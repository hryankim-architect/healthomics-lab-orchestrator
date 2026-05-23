"""End-to-end pipeline entry point.

This is the *pattern* that capability-portrait repos inherit. Each repo
replaces the body of ``run_pipeline`` with the actual bioinformatics work
(e.g. P3's VCF→HRD score, P1's Nextflow orchestration, P2's QC classifier,
P4's IHC + genomics calibration), but keeps the surrounding shape::

    audit_start  →  tracking_start  →  body  →  tracking_end  →  audit_end

The body must be deterministic enough that the canary smoke test exercises
the same code path with a fixture input.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import yaml

from healthomics_lab import audit, tracking


def _run_id(name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{name}-{stamp}"


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_manifest(manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    """Download every entry in the manifest; verify SHA-256 checksums."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    results: list[dict[str, Any]] = []
    for entry in manifest.get("inputs", []):
        url = entry["url"]
        rel = entry["path"]
        expected = entry.get("sha256")
        size_mb = entry.get("size_mb")
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and expected and _checksum(dest) == expected:
            results.append({"path": str(dest), "status": "cached"})
            continue

        urllib.request.urlretrieve(url, dest)
        actual = _checksum(dest)
        if expected and actual != expected:
            results.append({
                "path": str(dest),
                "status": "checksum_mismatch",
                "expected": expected,
                "actual": actual,
            })
            continue
        results.append({
            "path": str(dest),
            "status": "downloaded",
            "sha256": actual,
            "size_mb": size_mb,
        })

    return {"inputs": results}


def _run_nextflow(job_id: str, profile: str, project_dir: Path) -> int:
    """Invoke `nextflow run main.nf` as a subprocess.

    Inherits the parent process's environment so the launch wrapper
    (``scripts/run_lab.sh``) controls JAVA_HOME / PATH / etc.

    Returns the subprocess exit code. stdout and stderr stream to the
    parent process so the operator sees Nextflow's progress in real time.
    """
    cmd = [
        "nextflow",
        "run",
        str(project_dir / "main.nf"),
        "-profile",
        profile,
        "--job_id",
        job_id,
    ]
    proc = subprocess.run(cmd, cwd=project_dir, check=False)
    return proc.returncode


def run_pipeline(run_name: str, out_dir: Path) -> dict[str, Any]:
    """Run the chr22 RNA-seq capability portrait end-to-end.

    Wraps the Nextflow DSL2 pipeline (``main.nf``) in the substrate's
    audit + MLflow bracket so the run looks identical to every other
    capability-portrait repo from the substrate's perspective::

        audit_start -> tracking_start -> nextflow run -> post-mortem
                                                          -> tracking_end -> audit_end

    The Nextflow processes themselves also emit per-stage audit entries
    via ``healthomics_lab.process_hooks`` (16-18 entries per run on the
    n=3 demo cohort). The outer pipeline_start / pipeline_end pair bookends
    those, so the substrate sees a single hash-chained ledger covering both
    the orchestrator and every step inside it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    job_id = _run_id(run_name)
    project_dir = Path.cwd()

    audit.emit(
        action="pipeline_start",
        job_id=job_id,
        fields={"out_dir": str(out_dir), "project_dir": str(project_dir)},
    )

    metrics: dict[str, float] = {}
    exit_code: int = -1

    try:
        with tracking.run(name=job_id, experiment="healthomics_lab"):
            tracking.log_params({"run_name": run_name, "profile": "standard"})

            # Pre-flight: count samples for sanity log + sample-sheet visibility.
            samples_csv = project_dir / "data" / "samples.csv"
            if samples_csv.exists():
                with samples_csv.open(encoding="utf-8") as fh:
                    metrics["n_samples_input"] = float(sum(1 for _ in fh) - 1)

            # Body: the actual Nextflow pipeline.
            t0 = time.time()
            exit_code = _run_nextflow(job_id, "standard", project_dir)
            metrics["nextflow_wall_clock_seconds"] = time.time() - t0
            metrics["nextflow_exit_code"] = float(exit_code)

            # Post-mortem: audit chain length + validity.
            ledger = project_dir / "audit" / "local-demo.ndjson"
            if ledger.exists():
                ok, n_entries, _ = audit.verify(ledger)
                metrics["audit_chain_entries"] = float(n_entries)
                metrics["audit_chain_valid"] = 1.0 if ok else 0.0

            # Post-mortem: MultiQC report.
            mqc = project_dir / "results" / "multiqc" / "multiqc_report.html"
            if mqc.exists():
                metrics["multiqc_report_bytes"] = float(mqc.stat().st_size)
                tracking.log_artifact(str(mqc))

            tracking.log_metrics(metrics)
    finally:
        status = "success" if exit_code == 0 else "failed"
        audit.emit(
            action="pipeline_end",
            job_id=job_id,
            fields={
                "status": status,
                "metrics": metrics,
                "nextflow_exit_code": exit_code,
            },
        )

    return {
        "job_id": job_id,
        "status": "success" if exit_code == 0 else "failed",
        "metrics": metrics,
        "nextflow_exit_code": exit_code,
    }


@click.group()
def cli() -> None:
    """healthomics_lab capability-portrait pipeline."""


@cli.command()
@click.option(
    "--manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("data/manifest.yaml"),
)
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
)
def fetch(manifest: Path, out: Path) -> None:
    """Download public inputs declared in the manifest."""
    result = fetch_manifest(manifest, out)
    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--name", default="demo")
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("artifacts"),
)
def run(name: str, out: Path) -> None:
    """Run the end-to-end pipeline."""
    result = run_pipeline(name, out)
    click.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    cli()
