"""Incident triage using structured model output."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field

from .config import Settings

TRIAGE_INSTRUCTIONS = """\
You triage data pipeline incident signals for a revenue analytics stack (dbt, Airflow, DQ monitors).

Classify each incident into exactly one failure_type:
- schema_drift: dbt/database errors about missing or invalid columns, often after upstream schema changes.
- missing_partition: Airflow or ingestion failures when an expected date partition or export is absent.
- data_quality: DQ alerts where builds succeed but metric thresholds are breached (null rate, volume, etc.).
- freshness_sla: late upstream delivery or SLA-at-risk freshness, without a hard partition-missing error.
- unknown: cannot classify confidently from the signal.

Extract fields from the signal text only. Use null for fields not present or not applicable.
- object_name: failing dbt model, table, task target, or alert object (e.g. stg_orders, analytics.fct_revenue_daily).
- error_text: primary error, exception message, or alert message (concise, one string).
- timestamp: best incident timestamp in ISO-8601 UTC when available.
- column: column involved in schema or DQ issues.
- partition_date: affected partition date as YYYY-MM-DD when present.
"""


class FailureType(str, Enum):
    SCHEMA_DRIFT = "schema_drift"
    MISSING_PARTITION = "missing_partition"
    DATA_QUALITY = "data_quality"
    FRESHNESS_SLA = "freshness_sla"
    UNKNOWN = "unknown"


class SignalKind(str, Enum):
    DBT_LOG = "dbt_log"
    AIRFLOW_TRACEBACK = "airflow_traceback"
    DQ_ALERT_JSON = "dq_alert_json"
    UNKNOWN = "unknown"


class IncidentSignal(BaseModel):
    """Raw incident input with a detected signal format."""

    raw_text: str = Field(min_length=1)
    signal_kind: SignalKind


class TriageResult(BaseModel):
    """Structured triage output for downstream grounding and reasoning."""

    failure_type: FailureType
    object_name: str | None = None
    error_text: str | None = None
    timestamp: str | None = None
    column: str | None = None
    partition_date: str | None = None


class TriageError(RuntimeError):
    """Raised when triage or structured parsing fails."""


def triage(raw_text: str, *, settings: Settings | None = None) -> TriageResult:
    """Classify an incident signal and extract structured triage fields."""
    text = _load_incident_text(raw_text)
    signal = IncidentSignal(raw_text=text, signal_kind=_detect_signal_kind(text))
    active_settings = settings or Settings.from_env()

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=active_settings.project_endpoint,
        credential=credential,
    )
    try:
        openai_client = project_client.get_openai_client()
        response = openai_client.responses.parse(
            model=active_settings.model_name,
            instructions=TRIAGE_INSTRUCTIONS,
            input=_format_prompt(signal),
            text_format=TriageResult,
        )
    finally:
        project_client.close()
        credential.close()

    result = response.output_parsed
    if result is None:
        msg = "Model did not return structured triage output"
        raise TriageError(msg)
    return result


def _load_incident_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    if "\n" in stripped or len(stripped) > 260:
        return raw_text

    candidate = Path(stripped)
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    except OSError:
        return raw_text
    return raw_text


def _detect_signal_kind(text: str) -> SignalKind:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(payload, dict) and (
                "alert_id" in payload or "monitor" in payload or "metric" in payload
            ):
                return SignalKind.DQ_ALERT_JSON

    lowered = text.lower()
    if "traceback (most recent call last)" in lowered or "partitionnotfounderror" in lowered:
        return SignalKind.AIRFLOW_TRACEBACK
    if "dbt" in lowered or "database error in model" in lowered:
        return SignalKind.DBT_LOG
    return SignalKind.UNKNOWN


def _format_prompt(signal: IncidentSignal) -> str:
    return (
        f"Signal format: {signal.signal_kind.value}\n\n"
        "Incident signal:\n"
        f"{signal.raw_text}"
    )


def triage_heuristic(raw_text: str) -> TriageResult:
    """Deterministic triage for local/demo runs without a model call."""
    text = _load_incident_text(raw_text)
    kind = _detect_signal_kind(text)

    if kind == SignalKind.DQ_ALERT_JSON:
        payload = json.loads(text.strip())
        return TriageResult(
            failure_type=FailureType.DATA_QUALITY,
            object_name=payload.get("object"),
            error_text=payload.get("message"),
            timestamp=payload.get("timestamp"),
            column=payload.get("column"),
            partition_date=payload.get("partition_date"),
        )

    if kind == SignalKind.AIRFLOW_TRACEBACK:
        partition_match = re.search(r"date=(\d{4}-\d{2}-\d{2})", text)
        timestamp_match = re.search(
            r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\].*ERROR",
            text,
        )
        error_match = re.search(r"(\w+Error: .+)", text)
        return TriageResult(
            failure_type=FailureType.MISSING_PARTITION,
            object_name="extract_orders",
            error_text=error_match.group(1) if error_match else "partition not found",
            timestamp=f"{timestamp_match.group(1)}Z" if timestamp_match else None,
            partition_date=partition_match.group(1) if partition_match else None,
        )

    if kind == SignalKind.DBT_LOG:
        object_match = re.search(r"Database Error in model (\w+)", text, re.IGNORECASE)
        if not object_match:
            object_match = re.search(r"model [\w.]+\.(\w+)", text, re.IGNORECASE)
        column_match = re.search(r'column "(\w+)" does not exist', text, re.IGNORECASE)
        timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC", text)
        error_match = re.search(r'column "(\w+)" does not exist', text, re.IGNORECASE)
        return TriageResult(
            failure_type=FailureType.SCHEMA_DRIFT,
            object_name=object_match.group(1) if object_match else None,
            error_text=f'column "{error_match.group(1)}" does not exist' if error_match else None,
            timestamp=f"{timestamp_match.group(1)}Z" if timestamp_match else None,
            column=column_match.group(1) if column_match else None,
        )

    return TriageResult(failure_type=FailureType.UNKNOWN, error_text=text[:500])
