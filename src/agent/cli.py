"""Command-line entrypoint for the DataOps root-cause agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .audit import AuditTrace, record_audit
from .local_grounding import retrieve_local
from .local_pipeline import reason_heuristic, recommend_heuristic, verify_heuristic
from .prompts import build_retrieval_query
from .reasoner import reason
from .recommend import Recommendation, recommend
from .retrieval import RetrievalClient
from .triage import triage, triage_heuristic
from .verifier import verify

_REQUIRED_ENV = (
    "PROJECT_ENDPOINT",
    "SEARCH_ENDPOINT",
    "KNOWLEDGE_BASE_NAME",
    "KB_MCP_ENDPOINT",
    "MODEL_NAME",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent", description="DataOps root-cause agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose_parser = subparsers.add_parser("diagnose", help="Run end-to-end incident diagnosis")
    diagnose_parser.add_argument("path", type=Path, help="Incident log, traceback, or DQ alert path")
    diagnose_parser.add_argument(
        "--local",
        action="store_true",
        help="Use local knowledge grounding and heuristic steps (no Foundry calls)",
    )
    diagnose_parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Directory for audit JSON output",
    )

    args = parser.parse_args(argv)
    if args.command == "diagnose":
        return diagnose(args.path, local=args.local, runs_dir=args.runs_dir)
    return 1


def diagnose(path: Path, *, local: bool = False, runs_dir: Path = Path("runs")) -> int:
    incident_path = path.expanduser()
    if not incident_path.is_file():
        print(f"Incident file not found: {incident_path}", file=sys.stderr)
        return 1

    raw_text = incident_path.read_text(encoding="utf-8")
    load_dotenv()
    use_local = local or not _foundry_configured()
    if not local and use_local:
        print("Foundry not configured; running local diagnosis mode.", file=sys.stderr)

    try:
        if use_local:
            result, audit_path = _diagnose_local(raw_text, incident_path, runs_dir=runs_dir)
        else:
            result, audit_path = _diagnose_foundry(raw_text, runs_dir=runs_dir)
    except Exception as exc:
        print(f"Diagnosis failed: {exc}", file=sys.stderr)
        return 1

    _print_result(result)
    print(f"\nAudit log: {audit_path}")
    return 0


def _foundry_configured() -> bool:
    return all(os.getenv(name, "").strip() for name in _REQUIRED_ENV)


def _diagnose_foundry(raw_text: str, *, runs_dir: Path) -> tuple[Recommendation, Path]:
    triage_result = triage(raw_text)
    query = build_retrieval_query(triage_result)

    with RetrievalClient() as client:
        grounding = client.retrieve(query)
        candidates = reason(triage_result, grounding=grounding, retrieval_client=client)
        verified = verify(candidates, grounding, triage=triage_result, retrieval_client=client)
        recommendation = recommend(
            verified,
            grounding,
            triage=triage_result,
            retrieval_client=client,
        )
        audit_path = record_audit(
            AuditTrace(
                input_raw=raw_text,
                triage=triage_result,
                retrieval_query=query,
                grounding=grounding,
                hypotheses=candidates,
                verified=verified,
                recommendation=recommendation,
            ),
            runs_dir=runs_dir,
        )
    return recommendation, audit_path


def _diagnose_local(
    raw_text: str,
    incident_path: Path,
    *,
    runs_dir: Path,
) -> tuple[Recommendation, Path]:
    triage_result = triage_heuristic(str(incident_path))
    query = build_retrieval_query(triage_result)
    grounding = retrieve_local(query)
    candidates = reason_heuristic(triage_result, grounding)
    verified = verify_heuristic(candidates, grounding)
    recommendation = recommend_heuristic(verified, grounding, triage=triage_result)
    audit_path = record_audit(
        AuditTrace(
            input_raw=raw_text,
            triage=triage_result,
            retrieval_query=query,
            grounding=grounding,
            hypotheses=candidates,
            verified=verified,
            recommendation=recommendation,
        ),
        runs_dir=runs_dir,
    )
    return recommendation, audit_path


def _print_result(result: Recommendation) -> None:
    print(f"Root cause (confidence {result.confidence:.2f}):")
    print(result.root_cause)
    print("\nRecommended fix:")
    print(result.recommended_fix)
    print(f"\nAction type: {result.action_type} (not executed)")
    print("\nCitations:")
    for cite in result.citations:
        label = cite.doc_key or cite.ref_id
        print(f"  - [{cite.ref_id}] {label}")


if __name__ == "__main__":
    raise SystemExit(main())
