#!/usr/bin/env nextflow

/*
 * healthomics-lab-orchestrator — main.nf
 *
 * Capability-portrait RNA-seq pipeline. Mirrors the nf-core/rnaseq DAG shape
 * (FastQC -> align -> count -> MultiQC) on a chr22 subset reference so the
 * full demo runs in under five minutes on a single laptop.
 *
 * Every process embeds substrate hooks via `python -m healthomics_lab.process_hooks`
 * so a Polish-Phase5 lab node receives the same audit / MLflow signals as
 * every other capability-portrait repo in the quartet.
 *
 * See README.md for the "what this shows" framing and
 * docs/what-is-out-of-scope.md for the anti-scope-creep ledger.
 */

nextflow.enable.dsl = 2

// ---------------------------------------------------------------------------
// Workflow
// ---------------------------------------------------------------------------

workflow {

    // Parse the sample sheet into a channel of (sample_id, condition, [r1, r2])
    samples_ch = Channel
        .fromPath(params.samples, checkIfExists: true)
        .splitCsv(header: true)
        .map { row ->
            tuple(
                row.sample_id,
                row.condition,
                [ file(row.fastq_1, checkIfExists: true),
                  file(row.fastq_2, checkIfExists: true) ],
            )
        }

    // FastQC — runs once per sample on the raw paired-end FASTQs
    FASTQC( samples_ch )

    // HISAT2 — align paired-end reads to the chr22 reference
    HISAT2_ALIGN( samples_ch )

    // featureCounts — quantify per-gene reads from each aligned BAM
    FEATURECOUNTS( HISAT2_ALIGN.out.bam )

    // MultiQC — aggregate FastQC + HISAT2 alignment summary + featureCounts
    multiqc_inputs = FASTQC.out.report
        .map { _id, files -> files }
        .mix( HISAT2_ALIGN.out.summary )
        .mix( FEATURECOUNTS.out.summary )
        .collect()

    MULTIQC( multiqc_inputs )
}

// ---------------------------------------------------------------------------
// Processes
// ---------------------------------------------------------------------------

process FASTQC {
    tag { sample_id }

    input:
        tuple val(sample_id), val(condition), path(fastqs)

    output:
        tuple val(sample_id), path("${sample_id}_fastqc/*"), emit: report

    script:
    """
    python -m healthomics_lab.process_hooks emit \\
        --stage fastqc --status start \\
        --job-id ${params.job_id} --sample ${sample_id}

    mkdir -p ${sample_id}_fastqc
    fastqc --quiet --threads 2 --outdir ${sample_id}_fastqc ${fastqs.join(' ')}

    python -m healthomics_lab.process_hooks emit \\
        --stage fastqc --status end \\
        --job-id ${params.job_id} --sample ${sample_id}
    """

    stub:
    """
    mkdir -p ${sample_id}_fastqc
    touch ${sample_id}_fastqc/${sample_id}_1_fastqc.zip
    touch ${sample_id}_fastqc/${sample_id}_2_fastqc.zip
    """
}

process HISAT2_ALIGN {
    tag { sample_id }
    cpus params.threads_align

    input:
        tuple val(sample_id), val(condition), path(fastqs)

    output:
        tuple val(sample_id), path("${sample_id}.sorted.bam"), path("${sample_id}.sorted.bam.bai"), emit: bam
        path "${sample_id}.hisat2.summary.txt", emit: summary

    script:
    def (r1, r2) = fastqs
    """
    python -m healthomics_lab.process_hooks emit \\
        --stage hisat2_align --status start \\
        --job-id ${params.job_id} --sample ${sample_id}

    hisat2 \\
        -x ${params.hisat2_index} \\
        -1 ${r1} -2 ${r2} \\
        -p ${task.cpus} \\
        --summary-file ${sample_id}.hisat2.summary.txt \\
        --new-summary \\
        | samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam -

    samtools index ${sample_id}.sorted.bam

    # Parse overall alignment rate (last percentage on the summary line) and
    # log it as a metric. Falls back to 0.0 if the parse fails — the audit
    # entry always lands.
    align_pct=\$(awk -F'[(): ]+' '/Overall alignment rate/ {print \$5}' ${sample_id}.hisat2.summary.txt | tr -d '%')
    align_pct=\${align_pct:-0}

    python -m healthomics_lab.process_hooks emit \\
        --stage hisat2_align --status end \\
        --job-id ${params.job_id} --sample ${sample_id} \\
        --metric align_rate_pct=\${align_pct}
    """

    stub:
    """
    touch ${sample_id}.sorted.bam ${sample_id}.sorted.bam.bai
    printf 'HISAT2 summary\\nOverall alignment rate: 0.00%%\\n' > ${sample_id}.hisat2.summary.txt
    """
}

process FEATURECOUNTS {
    tag { sample_id }
    cpus params.threads_count

    input:
        tuple val(sample_id), path(bam), path(bai)

    output:
        tuple val(sample_id), path("${sample_id}.counts.tsv"), emit: counts
        path "${sample_id}.counts.tsv.summary", emit: summary

    script:
    """
    python -m healthomics_lab.process_hooks emit \\
        --stage featurecounts --status start \\
        --job-id ${params.job_id} --sample ${sample_id}

    # Decompress GTF on the fly if it's gzipped (subread/featureCounts wants
    # plain text). gzcat on macOS, zcat on Linux — both handle .gz here.
    gtf_in=${params.reference_gtf}
    if [[ "\$gtf_in" == *.gz ]]; then
        gunzip -c "\$gtf_in" > reference.gtf
        gtf_path=reference.gtf
    else
        gtf_path="\$gtf_in"
    fi

    featureCounts \\
        -T ${task.cpus} \\
        -a "\$gtf_path" \\
        -F GTF \\
        -t exon \\
        -g gene_id \\
        -p --countReadPairs \\
        -o ${sample_id}.counts.tsv \\
        ${bam}

    # Pull the assigned-read percentage from the .summary file as a metric.
    assigned=\$(awk '/^Assigned/ {print \$2}' ${sample_id}.counts.tsv.summary)
    total=\$(awk 'NR>1 {s+=\$2} END {print s+0}' ${sample_id}.counts.tsv.summary)
    if [[ "\$total" -gt 0 ]]; then
        pct=\$(awk -v a="\$assigned" -v t="\$total" 'BEGIN {printf "%.2f", (a/t)*100}')
    else
        pct=0
    fi

    python -m healthomics_lab.process_hooks emit \\
        --stage featurecounts --status end \\
        --job-id ${params.job_id} --sample ${sample_id} \\
        --metric assigned_pct=\${pct} \\
        --metric assigned_reads=\${assigned:-0}
    """

    stub:
    """
    printf 'Geneid\\tChr\\tStart\\tEnd\\tStrand\\tLength\\t${bam.simpleName}\\n' > ${sample_id}.counts.tsv
    printf 'Status\\t${bam.simpleName}\\nAssigned\\t0\\nUnassigned_Unmapped\\t0\\n' > ${sample_id}.counts.tsv.summary
    """
}

process MULTIQC {
    tag 'aggregate'

    input:
        path('inputs/*')

    output:
        path "multiqc_report.html", emit: report
        path "multiqc_data",        emit: data

    script:
    """
    python -m healthomics_lab.process_hooks emit \\
        --stage multiqc --status start \\
        --job-id ${params.job_id}

    # MultiQC lives in a dedicated conda env (lesson L-phi: libtiff soname
    # mismatch in the base env). The `conda run` form keeps PATH clean.
    conda run -n multiqc multiqc \\
        --force \\
        --filename multiqc_report.html \\
        --outdir . \\
        inputs/

    python -m healthomics_lab.process_hooks emit \\
        --stage multiqc --status end \\
        --job-id ${params.job_id}
    """

    stub:
    """
    mkdir -p multiqc_data
    touch multiqc_report.html
    """
}
