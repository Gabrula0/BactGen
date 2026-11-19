process QC_TRIM {
    tag "$sample_id"
    publishDir "${params.outdir}/qc", mode: 'copy', pattern: "*.{html,json}"

    input:
    tuple val(sample_id), path(r1), path(r2)

    output:
    tuple val(sample_id), path("${sample_id}_clean_R1.fastq.gz"), path("${sample_id}_clean_R2.fastq.gz"), emit: reads
    tuple val(sample_id), path("${sample_id}_fastp.json"), emit: json
    path "${sample_id}_fastp.html"

    script:
    """
    fastp \
        -i ${r1} -I ${r2} \
        -o ${sample_id}_clean_R1.fastq.gz \
        -O ${sample_id}_clean_R2.fastq.gz \
        --json ${sample_id}_fastp.json \
        --html ${sample_id}_fastp.html \
        --thread ${task.cpus}
    """
}
