#!/usr/bin/env bash
# Execute the capability-portrait pipeline on a Polish-Phase5 lab node.
#
# This wraps `make run` with the substrate environment variables set to the
# lab defaults, so audit entries flow to chi-mac-p:8081 and MLflow runs are
# tracked at chi-mac-p:5050. On a fresh checkout without the substrate
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
# Use mDNS .local hostnames so substrate hits prefer the LAN-direct path
# instead of routing through the Tailscale daemon. The substrate host's
# actual macOS LocalHostName is `chi-mac-p` (verify with `scutil --get
# LocalHostName` on the substrate host), which the SSH config may also
# expose under an alias (e.g. `chi-mac-m`). mDNS only knows the
# LocalHostName, never the SSH alias, so this default must use
# `chi-mac-p.local` regardless of which alias the operator uses to SSH
# in. Measured 2026-05-23 from chi-mac-i: chi-mac-p.local resolves to
# 192.168.86.10 and answers HTTP in ~24 ms over Wi-Fi LAN.
# Override by exporting AUDIT_HOST / MLFLOW_TRACKING_URI before invoking
# the wrapper if the worker node sits outside the LAN where .local
# resolves (e.g. roaming laptops); in that case the Tailscale magic-DNS
# name is the right value.
export AUDIT_HOST="${AUDIT_HOST:-chi-mac-p.local:8081}"
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://chi-mac-p.local:5050}"
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
