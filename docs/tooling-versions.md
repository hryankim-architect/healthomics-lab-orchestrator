# Hour 1 — Tooling Versions

## Installed and verified (2026-05-25 Monday afternoon, multiqc fixed evening)

| Tool | Version | Source |
|---|---|---|
| Java | 19.0.1 (brew) + 25.0.2 LTS (conda) | both available |
| Nextflow | 23.04.2 build 5870 | brew nextflow |
| HISAT2 | 2.2.2 | bioconda |
| samtools | 1.23.1 | bioconda |
| subread/featureCounts | 2.1.1 | bioconda |
| FastQC | 0.12.1 | bioconda |
| seqkit | 2.13.0 | bioconda |
| MultiQC | 1.35 ✅ (after libtiff fix) | bioconda + conda-forge libtiff |

## Lesson Lφ — conda runtime dylib mismatch
MultiQC install succeeded but `--version` threw `Library not loaded: libtiff.5.dylib`.
Root cause: PIL's `_imaging.cpython-312-darwin.so` was compiled against libtiff 5,
but conda installed libtiff 4.5.0 from the bioconda channel resolution.
Fix: `conda install -c conda-forge libtiff` pulls in libtiff 5+.

**Generalizing**: when a conda CLI tool errors on import with "Library not loaded",
it's almost always a native dep version mismatch — install the missing version
from conda-forge to fix.
