"""End-to-end smoke tests for the pipeline orchestration layer.

The actual Nextflow subprocess is stubbed (via monkeypatch on
``pipeline._run_nextflow``) so these tests run in any environment without
requiring Nextflow + Java + bioconda. The real-data smoke test lives in
``scripts/run_lab.sh``; these tests verify the *bracket* contract:

  - pipeline_start lands before any body work
  - pipeline_end lands even when the inner subprocess fails
  - tampering with the ledger is detected by audit.verify
"""

from __future__ import annotations

import json
from pathlib import Path

from healthomics_lab import audit, pipeline


def _stub_nextflow_exit(code: int):
    """Return a stub _run_nextflow that always exits with `code`."""

    def _stub(_job_id, _profile, _project_dir):
        return code

    return _stub


def test_pipeline_brackets_audit_around_nextflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setattr(pipeline, "_run_nextflow", _stub_nextflow_exit(0))

    result = pipeline.run_pipeline("smoke", tmp_path / "artifacts")

    assert result["status"] == "success"
    assert result["nextflow_exit_code"] == 0
    assert "nextflow_wall_clock_seconds" in result["metrics"]
    assert result["metrics"]["nextflow_exit_code"] == 0.0


def test_pipeline_records_failure_in_audit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setattr(pipeline, "_run_nextflow", _stub_nextflow_exit(7))

    result = pipeline.run_pipeline("failing-smoke", tmp_path / "artifacts")

    # try/finally must still emit pipeline_end on failure.
    assert result["status"] == "failed"
    assert result["nextflow_exit_code"] == 7

    ok, n_entries, _ = audit.verify()
    assert ok, "audit chain invalid after stubbed failure"
    assert n_entries == 2, "expected exactly pipeline_start + pipeline_end"


def test_audit_chain_is_valid_after_pipeline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setattr(pipeline, "_run_nextflow", _stub_nextflow_exit(0))

    pipeline.run_pipeline("smoke", tmp_path / "artifacts")

    ok, n_entries, first_bad = audit.verify()
    assert ok, f"audit chain invalid at {first_bad}"
    assert n_entries == 2  # exactly pipeline_start + pipeline_end with stubbed nextflow


def test_audit_chain_detects_tamper(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setattr(pipeline, "_run_nextflow", _stub_nextflow_exit(0))

    pipeline.run_pipeline("smoke", tmp_path / "artifacts")
    ledger = audit.DEFAULT_LEDGER

    # Tamper: rewrite the first entry in place.
    lines = ledger.read_text().splitlines()
    assert len(lines) >= 2
    tampered = json.loads(lines[0])
    tampered["fields"]["out_dir"] = "/etc/evil"
    lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    ledger.write_text("\n".join(lines) + "\n")

    ok, _, first_bad = audit.verify()
    assert not ok
    assert first_bad is not None
