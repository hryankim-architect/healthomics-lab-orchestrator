"""Per-Nextflow-process audit + MLflow hooks.

Each Nextflow process in ``main.nf`` runs in its own shell, so we cannot
share a Python process between stages. This module is invoked from inside
each process's ``script:`` block via the ``healthomics-emit`` CLI entry
point::

    python -m healthomics_lab.process_hooks emit \\
        --stage fastqc --status start \\
        --job-id ${params.job_id} --sample ${sample_id}

That call writes one NDJSON entry to the local audit ledger and, if
``MLFLOW_TRACKING_URI`` is set, logs the stage timing as a metric on the
parent MLflow run (run id taken from ``MLFLOW_RUN_ID`` so the per-process
calls all attach to the same run that ``pipeline.py`` opened).

Failure mode: the substrate side is best-effort. The audit entry always
lands locally; an MLflow exception is swallowed so a substrate hiccup
cannot break the pipeline.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import click

from healthomics_lab import audit, tracking


def _parse_metrics(raw: tuple[str, ...]) -> dict[str, float]:
    """Parse repeated ``--metric key=value`` flags into a float dict."""
    parsed: dict[str, float] = {}
    for item in raw:
        if "=" not in item:
            click.echo(f"warning: ignoring malformed --metric {item!r}", err=True)
            continue
        key, _, value = item.partition("=")
        try:
            parsed[key.strip()] = float(value.strip())
        except ValueError:
            click.echo(f"warning: ignoring non-numeric --metric {item!r}", err=True)
    return parsed


@click.group()
def cli() -> None:
    """healthomics_lab per-Nextflow-process substrate hooks."""


@cli.command()
@click.option("--stage", required=True, help="Pipeline stage name (fastqc, hisat2_align, ...).")
@click.option(
    "--status",
    required=True,
    type=click.Choice(["start", "end", "error"]),
    help="Lifecycle event for this stage.",
)
@click.option("--job-id", required=True, help="Stable pipeline run id (passed in by Nextflow).")
@click.option("--sample", default=None, help="Sample id this event pertains to (omit for aggregate stages).")
@click.option(
    "--metric",
    "metrics",
    multiple=True,
    help="Repeat for each numeric metric to log: --metric duration_seconds=12.4",
)
@click.option(
    "--ledger",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Override the local NDJSON ledger path. Resolution order: "
        "--ledger flag > $HEALTHOMICS_AUDIT_LEDGER env var > audit/local-demo.ndjson. "
        "Nextflow processes run in per-task work dirs, so set the env var to an "
        "absolute path so per-process entries all land in the same ledger."
    ),
)
def emit(
    stage: str,
    status: str,
    job_id: str,
    sample: str | None,
    metrics: tuple[str, ...],
    ledger: Path | None,
) -> None:
    """Emit one audit entry for a Nextflow process lifecycle event."""
    if ledger is None:
        env_ledger = os.environ.get("HEALTHOMICS_AUDIT_LEDGER")
        if env_ledger:
            ledger = Path(env_ledger)

    parsed_metrics = _parse_metrics(metrics)

    fields: dict[str, Any] = {
        "stage": stage,
        "status": status,
    }
    if sample:
        fields["sample"] = sample
    if parsed_metrics:
        fields["metrics"] = parsed_metrics

    action = f"{stage}_{status}"

    entry = audit.emit(
        action=action,
        job_id=job_id,
        fields=fields,
        ledger_path=ledger,
    )

    # Best-effort MLflow logging — only if both env vars are set so the per-
    # process calls attach to the parent run that pipeline.py opened.
    if (
        parsed_metrics
        and os.environ.get("MLFLOW_TRACKING_URI")
        and os.environ.get("MLFLOW_RUN_ID")
        and tracking.is_enabled()
    ):
        try:
            prefix = f"{stage}__{sample}" if sample else stage
            tracking.log_metrics(
                {f"{prefix}__{k}": v for k, v in parsed_metrics.items()}
            )
        except Exception as exc:  # noqa: BLE001 — substrate hiccup must not break pipeline
            click.echo(f"warning: mlflow log_metrics failed: {exc}", err=True)

    # Echo the action so Nextflow's .command.log captures what happened.
    click.echo(f"audit emit ok: action={action} job_id={job_id} sample={sample or '-'}")
    # Exit non-zero on logical inconsistencies so CI catches bad invocations.
    if entry.get("action") != action:
        sys.exit(2)


if __name__ == "__main__":
    cli()
