# What is out of scope (P1 — `healthomics-lab-orchestrator`)

This file is the anti-scope-creep ledger for the P1 capability portrait.
The repo's value comes from being *small and complete* — every item below
is something a reviewer might reasonably ask for that the v0.1 demo
deliberately does not attempt.

If a future PR proposes any of these, the contributor must answer one
question: **why is this still out of scope?** If the answer is good, edit
this file in the same PR. If not, the PR doesn't land.

---

## Full reference genome (whole GRCh38)

The demo runs against a chr22-only HISAT2 index (~62 MB). The full GRCh38
index would be ~4 GB and the per-sample alignment + featureCounts step
would balloon from sub-second to 5-15 minutes per sample.

**Why out of scope**: full-reference alignment would break the
"small and reproducible on a single workstation in under a minute"
contract that is the v0.1 capability claim. The orchestration question
(audit chain + MLflow + reproducible re-runs) is fully demonstrated on
the chr22 subset; expanding the reference adds runtime and download
budget without adding orchestration evidence. A production reference run
would swap two manifest URLs (`data/manifest.yaml`) and the rest of the
code is unchanged — that swap is intentionally cheap, but it is not the
demo.

---

## Differential expression analysis (DEG)

A real RNA-seq pipeline ends with DESeq2 / edgeR / limma-voom on the
featureCounts matrix to identify differentially expressed genes between
conditions. This demo stops at the per-sample count matrix.

**Why out of scope**: DEG is the *analytical* method, not the
*orchestration* capability. P3 (`tp53-aml-hrd-severity`) is the
capability-portrait repo for analytical methods; this one is the
orchestration portrait. Mixing them would dilute both. DEG would also
require a second statistical surface (multiple-testing correction
choices, design matrix specification, contrast definitions) that has
nothing to do with whether the Nextflow + audit + MLflow stack works.

---

## nf-core/rnaseq feature parity

nf-core/rnaseq ships with ~30 processes covering UMI deduplication,
multiple aligners (HISAT2 / STAR / salmon), quantification options
(featureCounts / Salmon / RSEM), QC suites (RSeQC / Qualimap /
preseq / dupRadar), and trimming variants. The demo runs four processes.

**Why out of scope**: feature parity with nf-core/rnaseq would re-implement
~5,000 lines of upstream Nextflow code and add ~20 GB of bioconda
dependencies. The capability portrait shows the *DSL2 + substrate wiring
pattern* on a minimal DAG that is faithful to the nf-core shape (FastQC ->
align -> count -> MultiQC). Anyone who has read nf-core/rnaseq can read
`main.nf` here and immediately recognize the pattern; that is the point.

---

## Container engine (Docker / Singularity / Apptainer)

nf-core pipelines normally run inside Docker or Singularity containers so
the bioinformatics tools come from immutable image layers, not the host's
package manager. This demo uses host-installed tools via bioconda + brew.

**Why out of scope**: container engines add a 5-15 GB image pull on first
run, require Docker Desktop or Singularity installation, and complicate
the "no cloud credentials, no GPU, single workstation" promise. The five
macOS-Nextflow lessons captured in `docs/tooling-versions.md` are the
*alternative* — a thin set of host-environment hardening rules that get
the same reproducibility without containers. Adding container support is
a v0.2+ task, and would be a fork of `nextflow.config` (`profiles { docker
{ ... } }`) rather than a rewrite.

---

## Multi-organism support

The demo is hard-coded to human GRCh38 chr22. A real pipeline configurable
for mouse (mm10/mm39), rat (rn7), or arabidopsis (TAIR10) would parametrize
the reference choice.

**Why out of scope**: multi-organism support adds a parameter
(`params.organism`), a manifest selector, and a test matrix that grows
with each species. It buys no orchestration evidence — the audit chain
and MLflow integration look identical regardless of organism. The
production version of this pipeline at Gilead supported four organisms;
the lab version proves the orchestration pattern, not the parametrization.

---

## Production HA / RBAC / multi-tenant isolation

The pipeline runs in a single Python process invoking a single Nextflow
subprocess on a single workstation. There is no high availability, no
role-based access control, no per-tenant resource isolation, no retry
backoff, no distributed orchestration.

**Why out of scope**: the substrate (`audit.py`, `tracking.py`,
`canary.py`) provides the building blocks; the capability portrait does
not re-implement Polish-Phase5 infrastructure. Production hardening
belongs to the substrate (or to a future deployment-tier repo), not to
the analytical / orchestration demo.

---

## Cloud cost optimization (AWS HealthOmics, Nextflow Tower)

A production RNA-seq pipeline on AWS HealthOmics or Nextflow Tower needs
spot-instance bidding, S3 lifecycle rules, intelligent task scheduling
(grouping small tasks to reduce per-task EC2 overhead), and a
cost-per-sample dashboard.

**Why out of scope**: the demo runs locally with zero cloud cost. The
orchestration pattern (DSL2 + audit + MLflow) is identical regardless of
executor; the AWS HealthOmics + Tower configuration is a deployment
choice that lives in `nextflow.config` profiles, not in the pipeline
logic. Adding a `healthomics` profile is a future v0.2+ task and would
require an AWS account in the loop, which breaks the "runnable by anyone
who clones the repo" promise.

---

## Real-time / streaming inputs

The demo reads pre-downloaded FASTQs from `data/fastq/`. A real clinical
pipeline often consumes streaming basecaller output (Illumina BCL, ONT
fast5/pod5) and runs alignment as reads arrive.

**Why out of scope**: streaming inputs add a basecaller dependency
(Illumina bcl2fastq, Guppy/Dorado for ONT) and an event-driven
orchestration layer (typically a message queue + a Nextflow `-resume`
loop). Neither belongs to a static-input capability portrait. The
audit-chain pattern this repo demonstrates would work with streaming
inputs unchanged; that's the point.

---

## Alternative aligners (STAR, salmon, kallisto, minimap2)

HISAT2 is one of several RNA-seq aligners. STAR is the de-facto standard
for differential-expression pipelines; salmon and kallisto bypass
alignment entirely with pseudoalignment + quantification. The demo uses
HISAT2 only.

**Why out of scope**: each additional aligner doubles the conda
dependency surface, requires a different index format, and produces a
different output (BAM vs. quant.sf vs. abundance.h5). The orchestration
capability is identical regardless of which aligner the
`HISAT2_ALIGN`-equivalent process wraps. Adding a second aligner is a
v0.2 PR that adds one process and one profile.

---

## L-beta2 fix: env-var injection into Nextflow cache key

Currently, `nextflow.config`'s `env { HEALTHOMICS_AUDIT_LEDGER = ... }`
block is *not* part of Nextflow's process cache key (lesson L-beta2 in
`docs/tooling-versions.md`). Changing the audit ledger path requires
`rm -rf work/` to invalidate the cache, which is documented but
operationally awkward.

**Why out of scope (for v0.1)**: the proper fix is to encode
substrate-related env vars into each process's `script:` body as
arguments (e.g. `--ledger ${params.audit_dir}/local-demo.ndjson`) so
Nextflow's hash sees them. That would add 4 lines per process and slightly
reduce readability. Deferred to v0.2 once the capability portrait has
been read by enough people to know whether the readability tradeoff is
worth it.

---

## Adding an item

Open a PR that:

1. Adds the item to the appropriate section above (or creates a new
   section if none fits).
2. Adds a one-sentence reason in italics for why it remains out of scope.
3. Links to the upstream feature request or issue if there is one.

That's it. The friction is intentional.
