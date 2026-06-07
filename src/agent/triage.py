"""Incident triage using structured model output."""

from __future__ import annotations

import json
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
    candidate = Path(raw_text.strip())
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
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
