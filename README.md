# `healthomics-lab-orchestrator`

*Public reference data is subsetted to chr22 only; the full GRCh38 run would exceed the single-workstation size constraint this demo is designed to satisfy.*

![ci](https://github.com/hryankim-architect/healthomics-lab-orchestrator/actions/workflows/ci.yml/badge.svg) ![english-only](https://github.com/hryankim-architect/healthomics-lab-orchestrator/actions/workflows/english-only.yml/badge.svg)

**What this shows**: an RNA-seq pipeline orchestrated via Nextflow DSL2 with
substrate-aware audit + MLflow hooks on every process, mirroring the
nf-core/rnaseq DAG shape (FastQC -> HISAT2 -> featureCounts -> MultiQC) on
commodity hardware.

**Reproducibility**: `make data && make run` completes in **~45 seconds** on
a single Mac/Linux box. No GPU, no Docker, no cloud credentials.

**Substrate**: emits a 22-entry NDJSON ledger with SHA-256 chaining across
both the outer Python orchestrator and every inner Nextflow process, tracks
MLflow per-run aggregate metrics, and exposes a canary smoke test that the
Polish-Phase5 `lab_semantic_check.py` probe can call.

**AWS HealthOmics context**: a production version of this orchestration
processed clinical RNA-seq cohorts at full reference scale on AWS HealthOmics
during my time directing clinical bioinformatics at Gilead. Audit integrity
was a hard requirement, not an option. This repo demonstrates the orchestration
engineering and substrate integration — not biology — see
[`docs/what-is-out-of-scope.md`](docs/what-is-out-of-scope.md).

---

## The orchestration question

Production clinical-genomics pipelines fail in ways that ML engineers rarely
see: not in the model, but in the bookkeeping. *Which sample broke at which
stage with which exit code at what wall-clock time*, replayable from a
tamper-evident ledger, is the difference between a pipeline that survives an
auditor and one that does not.

This repo codifies that pattern in the smallest credible end-to-end demo:

> A four-process Nextflow DSL2 pipeline (the same shape nf-core/rnaseq uses)
> wrapped in a Python orchestrator that brackets the run with a
> hash-chained audit ledger and MLflow tracking. Every Nextflow process
> emits its own start/end audit entry through a CLI substrate hook, so the
> resulting chain spans both the outer orchestrator and every inner step
> as a single linear history.

The pipeline runs FastQC -> HISAT2 alignment -> featureCounts -> MultiQC on
three downsampled Himes airway smooth muscle samples (SRA SRR1039508-512),
aligned against a chr22-only GRCh38 reference. The narrow reference is
intentional and is discussed in the scope-explicit section below.

---

## End-to-end pipeline

```
                            samples.csv (3 paired-end FASTQs)
                                       |
       Python orchestrator             |     Nextflow DSL2 (main.nf)
       (src/healthomics_lab/           |
        pipeline.py)                   |
                                       v
       pipeline_start  -->  +-------------------------+
       audit.emit          |  FASTQC      x 3 samples |--audit.emit (start/end)
                            +-------------------------+
       tracking.run().      |  HISAT2_ALIGN x 3        |--audit.emit (start/end)
       start_run()          +-------------------------+   + align_rate_pct metric
                            |  FEATURECOUNTS x 3       |--audit.emit (start/end)
                            +-------------------------+   + assigned_pct metric
                            |  MULTIQC (aggregate)     |--audit.emit (start/end)
                            +-------------------------+
                                       |
       _run_nextflow()  <--------------+
       returns exit code               |
                                       v
       Post-mortem:        +-------------------------+
       parse audit chain,  |  results/multiqc/        |
       MultiQC HTML size,  |  results/hisat2_align/   |
       wall-clock         |  results/featurecounts/  |
                            |  results/fastqc/         |
                            +-------------------------+
       tracking.log_metrics()
                                       |
       pipeline_end                    v
       audit.emit          audit/local-demo.ndjson   (22 entries, hash-chained)
```

Every Nextflow process invokes `python -m healthomics_lab.process_hooks emit`
in its `script:` block, before and after the actual bioinformatics tool. The
emit CLI writes to an absolute-path NDJSON ledger (configured via the
`HEALTHOMICS_AUDIT_LEDGER` env var, set by `nextflow.config`) so per-task
work-dir isolation does not fragment the chain.

If `AUDIT_HOST` is set, entries also POST to the substrate audit-API.
MLflow metrics flow to `MLFLOW_TRACKING_URI` if configured. Both default to
no-ops, so the demo runs cleanly on a fresh checkout without any substrate.

---

## Quickstart

```bash
# 0. Pre-flight (macOS, one-time)
#    System Java 19 is required; brew openjdk is NOT, see docs/tooling-versions.md.
#    Bioconda must provide fastqc/hisat2/samtools/featureCounts/seqkit in the
#    base env. MultiQC lives in a dedicated `multiqc` conda env (lesson L-phi).

# 1. Install pinned Python dependencies
make install                  # uv sync --extra dev

# 2. Fetch chr22 reference + 3 SRA samples (~110 MB; runs ~2 min on first call)
make data                     # populates data/reference/, data/fastq/

# 3. Run the end-to-end pipeline
#    macOS-specific: use scripts/run_lab.sh on chi-mac-p style hosts so the
#    conda Java 25 / venv python / bioconda PATH dance is handled for you.
scripts/run_lab.sh            # production form (substrate + macOS hardening)
# OR, after `conda deactivate; unset JAVA_HOME JAVA_CMD`:
make run                      # ~45 s on chi-mac-p; writes results/ + audit/

# 4. Run the test suite (Nextflow subprocess is stubbed; runs in ~2 s)
make test

# 5. Run the canary smoke test (substrate registration probe)
make canary
```

---

## Real-data climax (the proof)

End-to-end run on the n=3 chr22-only cohort, chi-mac-p, 2026-05-23:

| Pipeline metric | Value |
|---|---|
| Samples (paired-end, 1M reads each) | SRR1039508 / SRR1039509 / SRR1039512 |
| Wall-clock (fresh run, 4 stages x 3 samples + MultiQC) | **43.8 seconds** |
| Wall-clock (`-resume`, all 10 tasks cached) | ~8 seconds |
| HISAT2 alignment rate per sample | 3.69% / 3.50% / 3.46% |
| featureCounts assigned per sample | 31,118 / 29,319 / 29,388 (~3%) |
| MultiQC HTML | **2.4 MB**, 12 reports aggregated |
| Audit chain entries | **22** (1 pipeline_start + 20 per-process + 1 pipeline_end) |
| Audit chain hash-chain validity | **`ok=True`** (replay verifies every `prev_hash`) |
| Distinct audit action types | 10 (start + end pair for each of 5 stages) |
| Per-process MLflow metrics | `align_rate_pct`, `assigned_pct`, `assigned_reads` |
| Aggregate MLflow metrics | `nextflow_wall_clock_seconds`, `audit_chain_entries`, `multiqc_report_bytes` |

The 3-4% alignment rate is the *correct* number for a chr22-only reference
(chr22 is ~1.6% of GRCh38 by length, ~3% by expressed-transcript content).
Expected given the reference choice; see the scope section below.

---

## Sample `pipeline_end` audit entry (the actual proof)

The closing entry of the chain captures every aggregate metric and the chain
length itself, so a downstream consumer (e.g. the substrate's
`lab_semantic_check.py`) can sanity-check a run without re-reading the whole
ledger:

```json
{
  "action": "pipeline_end",
  "actor": "ryan@chi-mac-p",
  "fields": {
    "metrics": {
      "audit_chain_entries": 21.0,
      "audit_chain_valid": 1.0,
      "multiqc_report_bytes": 2433912.0,
      "n_samples_input": 3.0,
      "nextflow_exit_code": 0.0,
      "nextflow_wall_clock_seconds": 43.76
    },
    "nextflow_exit_code": 0,
    "status": "success"
  },
  "job_id": "demo-20260523-202818",
  "prev_hash": "4b2598cc3145aaa7a5fd4b06f9301791ae03dee0018b81200ffe66c6a094af1e",
  "ts": "2026-05-23T20:29:02Z"
}
```

(The `audit_chain_entries` field reads 21 inside the `pipeline_end` entry
because the count is taken *before* `pipeline_end` itself is written to the
ledger. Final on-disk length is 22. See
[`docs/architecture.md`](docs/architecture.md) for the fence-post detail.)

---

## Scope, why a chr22-only reference

The first draft of this demo planned for a full-reference run with the
~96% alignment rate that nf-core/rnaseq advertises on standard cohorts. Two
open-tier ceilings pushed the design to a chr22 subset:

1. **Reference download budget**: full GRCh38 + GENCODE is ~3.5 GB
   compressed and the HISAT2 full-genome index is ~4 GB. That balloons
   `make data` from 2 minutes to over an hour and exceeds the size target
   for a single-workstation demo.

2. **Runtime budget**: full-genome HISAT2 + featureCounts on 1M paired reads
   x 3 samples is ~15-25 minutes on a laptop. The chr22 subset completes in
   ~45 seconds, keeping the `make run` feedback loop tight for
   substrate-integration debugging.

So the v0.1 demo:

- Uses chr22 only (~50 MB FASTA, ~3 MB GTF, ~62 MB HISAT2 index = ~115 MB
  total reference plane).
- Expects a 3-4% alignment rate instead of ~96%; that is the chr22 share of
  expressed transcripts, not a defect.
- Makes no attempt to optimize that rate — the reference choice is fixed.

The 22-entry NDJSON ledger spanning both the outer orchestrator and inner
Nextflow processes is complete regardless of reference size. The orchestration
question is independent of the biological question.

A production reference run would replace exactly two manifest entries (the
chr22 FASTA and GTF URLs in `data/manifest.yaml`) and re-run `make data &&
make run`. Nothing in `main.nf` or `pipeline.py` changes.

---

## macOS-Nextflow integration lessons (the substrate war stories)

Hour-3 real-data smoke surfaced five cascading lessons specific to running
Nextflow on macOS in a conda + uv environment. All five are codified in
[`docs/tooling-versions.md`](docs/tooling-versions.md) and the relevant fixes
are landed in `nextflow.config` (`env { PATH = ... }`) and
`scripts/run_lab.sh`. Short index:

| ID | Symptom | Fix |
|---|---|---|
| **L-psi** | `Cannot find Java... up to 20` (Nextflow rejects conda Java 25) | `conda deactivate; unset JAVA_HOME JAVA_CMD` -> system Java 19 |
| **L-omega** | `.command.sh: line N: python: command not found` after L-psi fix | prepend `${projectDir}/.venv/bin` to `env.PATH` |
| **L-alpha2** | `.command.sh: line N: fastqc: command not found` after L-omega fix | append `${HOME}/miniconda3/bin` to `env.PATH` (after `/usr/bin` so Java order stays right) |
| **L-beta2** | All tasks show `cached: N` and env-var changes have no effect | Nextflow `-resume` cache key is script+inputs only; `rm -rf work/` or `scripts/run_lab.sh --fresh` |
| **L-chi** | `zsh: event not found:` in `git commit -m` | use `git commit -F <file>` with `<< 'EOF'` quoted heredoc (`!` triggers BANG_HIST even inside double-quotes) |

These are *not* mistakes the next contributor needs to rediscover. They are
documented to make the lab repo behave the same way on every macOS
workstation that runs `scripts/run_lab.sh`.

---

## Substrate environment variables

The substrate hooks read these at runtime; defaults are no-ops, so the demo
runs cleanly on a fresh checkout without the Polish-Phase5 substrate
present:

| Var | Default | What it does |
|---|---|---|
| `AUDIT_HOST` | unset | If set, audit entries POST to `http://${AUDIT_HOST}/events`. |
| `MLFLOW_TRACKING_URI` | unset | If set, MLflow runs are tracked at this URI. |
| `HEALTHOMICS_AUDIT_LEDGER` | unset (Python default = `audit/local-demo.ndjson`) | Set by `nextflow.config` to an absolute path so per-process emits land in a single ledger across Nextflow's per-task work dirs. |
| `HEALTHOMICS_LAB_RUN_NAME` | derived (`lab-<UTC-stamp>`) | Overrides the run name in audit + MLflow entries. |
| `HEALTHOMICS_LAB_CANARY_FIXTURE` | `tests/fixtures/canary.json` | Path used by `canary.py` for the deterministic smoke test. |

On a Polish-Phase5 lab node, `scripts/run_lab.sh` exports the substrate
endpoints (`chi-mac-m:8081`, `chi-mac-m:5050`) before invoking `make run`.

---

## Repo layout

```
.
├── README.md                       # This file
├── LICENSE                         # MIT
├── Makefile                        # install | data | run | test | report | canary | clean
├── pyproject.toml                  # uv-managed; pinned versions
├── nextflow.config                 # params + profiles + env (PATH, audit ledger)
├── main.nf                         # DSL2 workflow + 4 processes (with stub: blocks)
├── .github/workflows/
│   ├── ci.yml                      # ruff + pytest + scope-preamble lint
│   └── english-only.yml            # CJK character scanner
├── data/
│   ├── samples.csv                 # Nextflow input sheet (committed)
│   ├── manifest.yaml               # SHA-256 manifest of reference + FASTQ URLs
│   └── (raw data git-ignored)
├── src/healthomics_lab/
│   ├── audit.py                    # NDJSON hash-chained ledger emit + verify
│   ├── tracking.py                 # MLflow run wrapper (no-op fallback)
│   ├── canary.py                   # deterministic substrate smoke test
│   ├── process_hooks.py            # `healthomics-emit` CLI used by main.nf
│   └── pipeline.py                 # outer orchestrator (wraps `nextflow run`)
├── tests/                          # pytest suite (Nextflow stubbed)
│   ├── fixtures/canary.json
│   └── test_*.py
├── docs/
│   ├── architecture.md             # substrate integration diagram + fence-post note
│   ├── tooling-versions.md         # tool versions + 5 lessons (L-phi/psi/omega/alpha2/beta2/chi)
│   └── what-is-out-of-scope.md     # scope boundary ledger
└── scripts/
    ├── run_lab.sh                  # macOS-hardened launch wrapper (--fresh flag)
    └── check_english_only.py       # CJK scanner used by CI
```

---

## What this repo does not do

See [`docs/what-is-out-of-scope.md`](docs/what-is-out-of-scope.md) for the
full ledger. Short version: no full-reference alignment, no differential
expression analysis, no multi-organism support, no Docker/Singularity
container engine, no nf-core/rnaseq feature parity, no cloud cost
optimization, no production HA. Those belong to the production version of
this orchestration.

---

## Lineage

This repo was created from
[`bioinformatics-repo-scaffold-template`](https://github.com/hryankim-architect/bioinformatics-repo-scaffold-template),
the shared scaffold that every P-series repo in the quartet
(P1 / P2 / P3 / P4) inherits. The substrate modules (`audit.py`,
`tracking.py`, `canary.py`, `process_hooks.py`) are designed to be
copy-and-edit, not pip-installed, so each repo can diverge as needed
without coordinating releases.

---

## License

MIT. See [`LICENSE`](LICENSE).
