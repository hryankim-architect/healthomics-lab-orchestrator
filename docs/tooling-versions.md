# Hour 1 + 1.5 — Tooling Versions

## Installed and verified (2026-05-25 Monday, post-multiqc-fix-v2)

| Tool | Version | Source / Env |
|---|---|---|
| Java | 19.0.1 (brew) + 25.0.2 LTS (conda) | both available; Nextflow uses brew Java 19 |
| Nextflow | 23.04.2 build 5870 | brew nextflow |
| HISAT2 | 2.2.2 | bioconda (base) |
| samtools | 1.23.1 | bioconda (base) |
| subread/featureCounts | 2.1.1 | bioconda (base) |
| FastQC | 0.12.1 | bioconda (base) |
| seqkit | 2.13.0 | bioconda (base) |
| **MultiQC** | **1.35** | **dedicated `multiqc` env (`conda run -n multiqc multiqc ...`)** |

## Lesson Lφ — conda runtime dylib mismatch (final root cause)

MultiQC install in base env failed because PIL's `_imaging.cpython-312-darwin.so`
was compiled against libtiff with soname `.5`, but bioconda's libtiff in base
env shipped soname `.6`. Two attempted fixes did NOT work:

1. `conda install -c conda-forge libtiff` — no-op (already present at newer version).
2. `conda install --force-reinstall pillow` — reinstalled pillow but still bound
   to old libtiff soname (likely from cached prebuilt wheel that conda didn't
   rebuild).

**Working fix**: dedicated env via `conda create -n multiqc -c bioconda -c
conda-forge multiqc -y`. Fresh env gets a clean dependency resolution where
bioconda's multiqc + conda-forge's libtiff are co-installed with consistent
sonames. Invocation: `conda run -n multiqc multiqc <args>`.

**Generalizing**: when base env conda solver leaves a runtime mismatch and
force-reinstall doesn't fix it, a fresh dedicated env is the bulletproof
fallback. The cost is one extra `conda run -n <env>` prefix or env activation.
