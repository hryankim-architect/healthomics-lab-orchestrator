#!/usr/bin/env bash
# Execute the RNA-seq orchestration pipeline on a lab node.
#
# This wraps `make run` with the substrate environment variables set to the
# lab defaults, so audit entries flow to chi-mac-m:8081 and MLflow runs are
# tracked at chi-mac-m:5050. On a fresh checkout without the substrate
# present, run `make run` directly instead.
#
# macOS-specific environment hardening (lessons L-psi / L-omega / L-alpha2 /
# L-beta2, captured during Hour 3 real-data smoke):
#
#   - (base) conda env exports a JAVA_HOME that points at miniconda Java 25,
#     which Nextflow 23.04 rejects ("Java 8 or later, up to 20"). We
#     `conda deactivate` and unset JAVA_HOME / JAVA_CMD so the system Java
#     19.0.1 at /usr/bin/java is used.
#
#   - `conda deactivate` also removes the conda python and the bioconda CLIs
#     (fastqc / hisat2 / samtools / featureCounts / seqkit) from PATH.
#     nextflow.config compensates by prepending both ${projectDir}/.venv/bin
#     and ${HOME}/miniconda3/bin to every process's PATH, so each task sees
#     all four tool families (venv python, brew nextflow, system Java 19,
#     conda bioinformatics).
#
#   - Substrate-related env vars (notably HEALTHOMICS_AUDIT_LEDGER) flow
#     through nextflow.config's env { } block. Note that Nextflow's -resume
#     cache key is script + inputs only; env-var changes do NOT invalidate
#     cached tasks. After tweaking env vars, run `rm -rf work/ .nextflow/`
#     before re-running, or this wrapper's --fresh flag below.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
FRESH=0
for arg in "$@"; do
    case "$arg" in
        --fresh)
            FRESH=1
            ;;
        --help|-h)
            cat <<HELP
Usage: $(basename "$0") [--fresh]

Options:
  --fresh   Wipe work/ and results/ before running. Required when env vars
            change, since Nextflow -resume cache key ignores env vars (L-beta2).
HELP
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1 — macOS environment hardening (lessons L-psi / L-omega / L-alpha2)
# ---------------------------------------------------------------------------
echo "[run_lab] macOS env hardening: conda deactivate + unset JAVA_HOME/JAVA_CMD"

# Source conda's shell hook so `conda deactivate` works even if this script is
# invoked from a non-interactive shell. Skip silently if conda is not on PATH.
if command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    eval "$(conda shell.bash hook 2>/dev/null)" || true
    conda deactivate 2>/dev/null || true
fi
unset JAVA_HOME JAVA_CMD

# Sanity-print so the launch log captures what Java actually wins.
java -version 2>&1 | head -1 | sed 's/^/[run_lab] java: /'

# ---------------------------------------------------------------------------
# Step 2 — substrate endpoints (lab defaults; override per host if needed)
# ---------------------------------------------------------------------------
# Substrate host is `chi-mac-m` (where the audit-API and MLflow services run),
# matching every other repo in the lab and this repo's README. Override per host
# by exporting AUDIT_HOST / MLFLOW_TRACKING_URI before invoking the wrapper —
# e.g. the Tailscale magic-DNS name when the worker sits outside the LAN, or the
# host's mDNS `.local` form if you want the LAN-direct path.
export AUDIT_HOST="${AUDIT_HOST:-chi-mac-m:8081}"
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://chi-mac-m:5050}"
export HEALTHOMICS_LAB_RUN_NAME="${HEALTHOMICS_LAB_RUN_NAME:-lab-$(date -u +%Y%m%d-%H%M%S)}"

# ---------------------------------------------------------------------------
# Step 3 — sanity check + optional fresh-work cleanup (L-beta2)
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv not found on PATH" >&2
    exit 2
fi

if [[ $FRESH -eq 1 ]]; then
    echo "[run_lab] --fresh: wiping work/ results/ .nextflow.log* .nextflow/"
    rm -rf work/ results/ .nextflow.log* .nextflow/
fi

# ---------------------------------------------------------------------------
# Step 4 — run
# ---------------------------------------------------------------------------
echo "[run_lab] AUDIT_HOST=${AUDIT_HOST}"
echo "[run_lab] MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI}"
echo "[run_lab] RUN_NAME=${HEALTHOMICS_LAB_RUN_NAME}"

uv run make run RUN_NAME="${HEALTHOMICS_LAB_RUN_NAME}"

# ---------------------------------------------------------------------------
# Step 5 — post-run: invoke canary for substrate registration
# ---------------------------------------------------------------------------
echo "[run_lab] canary check"
uv run python -m healthomics_lab.canary

echo "[run_lab] done"
