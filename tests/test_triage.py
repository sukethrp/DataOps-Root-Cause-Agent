"""Tests for incident triage classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.triage import FailureType, triage_heuristic

INCIDENTS = Path(__file__).resolve().parent.parent / "incidents"


@pytest.mark.parametrize(
    ("fixture_name", "failure_type", "object_name", "column", "partition_date"),
    [
        (
            "incident-01-dbt-failure.log",
            FailureType.SCHEMA_DRIFT,
            "stg_orders",
            "amount",
            None,
        ),
        (
            "incident-02-airflow-traceback.txt",
            FailureType.MISSING_PARTITION,
            "extract_orders",
            None,
            "2026-06-11",
        ),
        (
            "incident-03-dq-alert.json",
            FailureType.DATA_QUALITY,
            "analytics.fct_revenue_daily",
            "order_amount",
            "2026-06-12",
        ),
    ],
)
def test_triage_heuristic_classifies_fixture(
    fixture_name: str,
    failure_type: FailureType,
    object_name: str,
    column: str | None,
    partition_date: str | None,
) -> None:
    result = triage_heuristic(str(INCIDENTS / fixture_name))

    assert result.failure_type == failure_type
    assert result.object_name == object_name
    if column is not None:
        assert result.column == column
    if partition_date is not None:
        assert result.partition_date == partition_date
    assert result.error_text
