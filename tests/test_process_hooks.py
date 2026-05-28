"""Unit + CLI tests for the per-Nextflow-process substrate hooks.

`process_hooks.emit` is the entry point each Nextflow process shells out to. We
test (1) the metric-string parser in isolation and (2) the `emit` CLI end to
end via Click's runner, writing to a temp ledger so no substrate is required.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from healthomics_lab import audit, process_hooks


def test_parse_metrics_keeps_numeric_drops_garbage() -> None:
    parsed = process_hooks._parse_metrics(
        ("duration_seconds=12.4", "reads=1000000", "bad_no_eq", "nan_value=abc")
    )
    assert parsed == {"duration_seconds": 12.4, "reads": 1000000.0}


def test_parse_metrics_empty() -> None:
    assert process_hooks._parse_metrics(()) == {}


def test_emit_writes_one_audit_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    ledger = tmp_path / "ledger.ndjson"

    result = CliRunner().invoke(
        process_hooks.cli,
        [
            "emit", "--stage", "fastqc", "--status", "start",
            "--job-id", "job-123", "--sample", "SRR1039508",
            "--metric", "duration_seconds=3.2",
            "--ledger", str(ledger),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "audit emit ok" in result.output

    lines = [ln for ln in ledger.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "fastqc_start"
    assert entry["fields"]["sample"] == "SRR1039508"
    assert entry["fields"]["metrics"] == {"duration_seconds": 3.2}


def test_emit_chain_is_valid_across_stages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AUDIT_HOST", raising=False)
    ledger = tmp_path / "ledger.ndjson"
    runner = CliRunner()
    for stage, status in [("fastqc", "start"), ("fastqc", "end"), ("hisat2_align", "start")]:
        r = runner.invoke(
            process_hooks.cli,
            ["emit", "--stage", stage, "--status", status,
             "--job-id", "job-9", "--ledger", str(ledger)],
        )
        assert r.exit_code == 0, r.output

    ok, n_entries, first_bad = audit.verify(ledger)
    assert ok, f"chain invalid at {first_bad}"
    assert n_entries == 3
