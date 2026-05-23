# Hour 1 — Tooling Versions

## Installed and verified (2026-05-25 Monday afternoon)

| Tool | Version | Source |
|---|---|---|
| Java | 19.0.1 (brew) and 25.0.2 LTS (conda) | brew openjdk + conda openjdk |
| Nextflow | 23.04.2 build 5870 | brew nextflow |
| HISAT2 | 2.2.2 | bioconda |
| samtools | 1.23.1 | bioconda |
| subread/featureCounts | 2.1.1 | bioconda |
| FastQC | 0.12.1 | bioconda |
| seqkit | 2.13.0 | bioconda |
| MultiQC | 1.35 installed but throws traceback on --version; needs investigation | bioconda |

## Notes
- Bioconda is the chosen distribution for bioinformatics CLI tools (vs brewsci/bio
  which lacks several of these on macOS arm64).
- Java 19 (brew) is the active runtime for Nextflow; Java 25 (conda) sits alongside.
- MultiQC fix deferred to Hour 2: investigate Python ABI mismatch from base conda
  env update.
