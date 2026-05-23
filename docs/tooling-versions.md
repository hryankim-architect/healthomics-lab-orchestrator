# Tooling Versions

## Installed and verified (Hour 1 -> Hour 3 real-data smoke complete)

| Tool | Version | Source / Env | Notes |
|---|---|---|---|
| Java | 19.0.1 | `/usr/bin/java` (system) | Nextflow-compatible; see L-psi |
| Java (also present) | 25.0.2 LTS | conda base (`~/miniconda3/lib/jvm`) | Nextflow 23.04 rejects; see L-psi |
| Nextflow | 23.04.2 build 5870 | brew | `/opt/homebrew/bin/nextflow` |
| HISAT2 | 2.2.2 | bioconda (base) | `~/miniconda3/bin/hisat2` |
| samtools | 1.23.1 | bioconda (base) | |
| subread/featureCounts | 2.1.1 | bioconda (base) | |
| FastQC | 0.12.1 | bioconda (base) | |
| seqkit | 2.13.0 | bioconda (base) | |
| **MultiQC** | **1.35** | **dedicated `multiqc` env (`conda run -n multiqc multiqc ...`)** | see L-phi |
| Python | 3.12.13 | `.venv/bin/python` (uv-managed) | hosts the `healthomics_lab` package |

## Tool path resolution at process launch

`nextflow.config` defines an `env { PATH = ... }` block so every Nextflow
task sees the four tool families that this pipeline needs:

```
${projectDir}/.venv/bin    -> venv python + healthomics_lab (substrate hooks)
/opt/homebrew/bin           -> brew nextflow + brew CLIs
/usr/bin                    -> system Java 19.0.1 (Nextflow-compatible)
${HOME}/miniconda3/bin      -> bioconda tools + conda CLI (for `conda run -n multiqc`)
${parent shell PATH}        -> everything else
```

Note that `/usr/bin` is placed before `~/miniconda3/bin` so system Java 19
wins over miniconda Java 25 in PATH lookup. The `scripts/run_lab.sh` wrapper
additionally runs `conda deactivate` and `unset JAVA_HOME JAVA_CMD` before
invoking Nextflow, because conda's shell hook will otherwise re-export
JAVA_HOME pointing at miniconda Java 25 regardless of PATH order.

## Lessons learned (Hour 3 real-data smoke)

### L-phi — conda runtime dylib mismatch (Hour 1.5)

MultiQC install in base env failed because PIL's
`_imaging.cpython-312-darwin.so` was compiled against libtiff with soname
`.5`, but bioconda's libtiff in base env shipped soname `.6`. Two attempted
fixes did NOT work:

1. `conda install -c conda-forge libtiff` — no-op (already present at newer
   version).
2. `conda install --force-reinstall pillow` — reinstalled pillow but still
   bound to old libtiff soname (likely from cached prebuilt wheel that conda
   did not rebuild).

**Working fix**: dedicated env via `conda create -n multiqc -c bioconda -c
conda-forge multiqc -y`. Fresh env gets a clean dependency resolution where
bioconda's multiqc + conda-forge's libtiff are co-installed with consistent
sonames. Invocation: `conda run -n multiqc multiqc <args>`.

**Generalizing**: when base env conda solver leaves a runtime mismatch and
force-reinstall does not fix it, a fresh dedicated env is the bulletproof
fallback. The cost is one extra `conda run -n <env>` prefix or env
activation.

### L-psi — macOS conda Java 25 vs Nextflow 23.04

When the user is in the `(base)` conda env (the default macOS prompt), conda
exports `JAVA_HOME=$HOME/miniconda3/lib/jvm` pointing at miniconda's Java 25
LTS. Nextflow 23.04 rejects it: `Cannot find Java or it is a wrong version
-- please make sure that Java 8 or later (up to 20) is installed`.

**Fix**: `conda deactivate; unset JAVA_HOME JAVA_CMD`. Then Nextflow falls
back to `/usr/bin/java`, which is the system Java 19.0.1 (Nextflow-compatible).
No brew openjdk install required — the system Java was already there.

### L-omega — `conda deactivate` removes venv python

`conda deactivate` also takes the conda python off PATH, which breaks per-
process substrate hooks like `python -m healthomics_lab.process_hooks emit`.
Symptom: `.command.sh: line N: python: command not found` in the first
Nextflow task's `.command.err`.

**Fix**: `nextflow.config` prepends `${projectDir}/.venv/bin` to every
process's PATH via the `env { }` block. The venv python is uv-managed and
already has the `healthomics_lab` package installed editable, so
`python -m healthomics_lab.process_hooks` resolves both the interpreter and
the package.

### L-alpha2 — `conda deactivate` removes bioconda CLIs

Same root cause as L-omega: `conda deactivate` takes `~/miniconda3/bin` off
PATH, so `fastqc`, `hisat2`, `samtools`, `featureCounts`, `seqkit` all
disappear too. Symptom: `.command.sh: line N: fastqc: command not found`
on the second task that runs after the substrate-hook fix lands.

**Fix**: same `env { PATH = ... }` block in `nextflow.config` also includes
`${HOME}/miniconda3/bin`, placed AFTER `/usr/bin` so system Java 19 still
wins over miniconda Java 25 in PATH lookup. All four tool families now
co-exist in process PATH without re-activating the conda env.

### L-beta2 — Nextflow -resume cache key ignores env vars

After tweaking `nextflow.config` env vars (especially `HEALTHOMICS_AUDIT_LEDGER`),
running with `-resume` does NOT re-execute the cached tasks — Nextflow's
process cache key is computed from the script body + inputs hash only.
Symptom: `[xx/yyyyyy] process > FASTQC (...) [100%] 3 of 3, cached: 3` for
all stages, but the changed env var has no observable effect because no
task actually ran.

**Fix**: wipe `work/` and `.nextflow/` before re-running, or use the
`scripts/run_lab.sh --fresh` flag. Long-term: substrate-related env vars
should also be encoded into the process script body (e.g. as
`--ledger ${params.audit_dir}/local-demo.ndjson`) so Nextflow's hash sees
them. Held off for v0.1 to keep main.nf readable.

### L-chi — `!` in commit-message body triggers zsh BANG_HIST

When the commit message body contains `!` (e.g. `!samples.csv` inside a
.gitignore explanation), zsh's history expansion fires at parse time —
even inside double-quoted strings, even when the `!` is preceded by
`set +H` on a previous line of the same multi-line paste, because zsh
parses the whole paste before the `set +H` takes effect.

**Fix**: use `git commit -F <file>` with a quoted heredoc body. Heredocs
with `<< 'EOF'` (single-quoted delimiter) suppress all shell expansion
on the body, including history expansion.
