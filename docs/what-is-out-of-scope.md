# What is out of scope — `healthomics-lab-orchestrator`

This file tracks deliberate scope boundaries for the P1 orchestration demo.
Keeping the demo small is deliberate. Every item below is something a
reviewer might reasonably ask for that the v0.1 demo does not attempt.

Want to move one of these in scope? The PR has to make the case for why it
was excluded in the first place. If the case is convincing, edit this file
alongside the change. Otherwise it stays out.

---

## Full reference genome (whole GRCh38)

The demo runs against a chr22-only HISAT2 index (~62 MB). The full GRCh38
index would be ~4 GB and the per-sample alignment + featureCounts step
would balloon from sub-second to 5-15 minutes per sample.

**Why out of scope**: full-reference alignment would exceed the size and
runtime target for this demo (~45 seconds on a single workstation). The
orchestration mechanics — audit chain, MLflow, reproducible re-runs — are
fully exercised on the chr22 subset. Expanding the reference adds download
and runtime cost without adding orchestration evidence. A production
reference run swaps two manifest URLs in `data/manifest.yaml`; nothing in
`main.nf` or `pipeline.py` changes.

---

## Differential expression analysis (DEG)

A real RNA-seq pipeline ends with DESeq2 / edgeR / limma-voom on the
featureCounts matrix to identify differentially expressed genes between
conditions. This demo stops at the per-sample count matrix.

**Why out of scope**: DEG is the *analytical* method, not the
*orchestration* capability. The analytical-method work lives in a separate
repo; this one demonstrates orchestration. Mixing them would dilute both.
DEG would also require a second statistical surface (multiple-testing
correction choices, design matrix specification, contrast definitions)
that has nothing to do with whether the Nextflow + audit + MLflow stack
works.

---

## nf-core/rnaseq feature parity

nf-core/rnaseq ships with ~30 processes covering UMI deduplication,
multiple aligners (HISAT2 / STAR / salmon), quantification options
(featureCounts / Salmon / RSEM), QC suites (RSeQC / Qualimap /
preseq / dupRadar), and trimming variants. The demo runs four processes.

**Why out of scope**: feature parity with nf-core/rnaseq would re-implement
~5,000 lines of upstream Nextflow code and add ~20 GB of bioconda
dependencies. This repo shows the *DSL2 + substrate wiring pattern* on a
minimal DAG faithful to the nf-core shape (FastQC -> align -> count ->
MultiQC). Anyone who has read nf-core/rnaseq will recognize the pattern
immediately; that is the point.

---

## Container engine (Docker / Singularity / Apptainer)

nf-core pipelines normally run inside Docker or Singularity containers so
the bioinformatics tools come from immutable image layers, not the host's
package manager. This demo uses host-installed tools via bioconda + brew.

**Why out of scope**: container engines add a 5-15 GB image pull on first
run, require Docker Desktop or Singularity installation, and complicate
the "no cloud credentials, no GPU, single workstation" promise. The five
macOS-Nextflow lessons captured in `docs/tooling-versions.md` are the
*alternative*, a thin set of host-environment hardening rules that get
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
with each species. The audit chain and MLflow integration are identical
regardless of organism. The production version of this pipeline at Gilead
supported four organisms; this demo verifies the orchestration pattern, not
the parametrization.

---

## Production HA / RBAC / multi-tenant isolation

The pipeline runs in a single Python process invoking a single Nextflow
subprocess on a single workstation. There is no high availability, no
role-based access control, no per-tenant resource isolation, no retry
backoff, no distributed orchestration.

**Why out of scope**: the substrate (`audit.py`, `tracking.py`, `canary.py`)
provides the building blocks. Production hardening belongs to the substrate
or to a future deployment-tier repo, not to this orchestration demo.

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

**Why out of scope**: streaming inputs require a basecaller (Illumina
bcl2fastq, Guppy/Dorado for ONT) and an event-driven orchestration layer
(typically a message queue + a Nextflow `-resume` loop). Neither fits a
static-input demo. The audit-chain pattern this repo demonstrates would
work with streaming inputs unchanged.

---

## Alternative aligners (STAR, salmon, kallisto, minimap2)

HISAT2 is one of several RNA-seq aligners. STAR is the de-facto standard
for differential-expression pipelines; salmon and kallisto bypass
alignment entirely with pseudoalignment + quantification. The demo uses
HISAT2 only.

**Why out of scope**: each additional aligner doubles the conda dependency
surface, requires a different index format, and produces different output
(BAM vs. quant.sf vs. abundance.h5). The orchestration wiring is identical
regardless of which aligner wraps the `HISAT2_ALIGN`-equivalent process.
Adding a second aligner is a v0.2 PR: one process, one profile.

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
reduce readability. Deferred to v0.2; the tradeoff is whether the extra verbosity per process
is worth the cleaner cache invalidation behavior.

---

## Adding an item

Open a PR that does three things:

1. Places the new item in the matching section above, or opens a new
   section if nothing fits.
2. Includes a one-sentence rationale (in italics) explaining why it stays
   out of scope at this stage.
3. Links the upstream issue or feature request if one exists.

Keep the bar high. The point of this file is to prevent scope from
expanding without a written reason. A PR that skips the rationale will not
land.
