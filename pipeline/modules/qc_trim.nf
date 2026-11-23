process QC_TRIM {
    tag "$sample_id"
    publishDir "${params.outdir}/qc", mode: 'copy', pattern: "*.{html,json}"

    input:
    tuple val(sample_id), path(r1), path(r2)

    output:
    tuple val(sample_id), path("${sample_id}_clean_R1.fastq.gz"), path("{${sample_id}_clean_R2.fastq.gz,NO_FILE_R2}"), emit: reads
    tuple val(sample_id), path("${sample_id}_fastp.json"), emit: json
    path "${sample_id}_fastp.html"

    script:
    if (!(sample_id ==~ /^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,49}$/)) {
        error "Invalid sample_id format: ${sample_id}"
    }
    def is_paired = r2 && !r2.name.startsWith('NO_FILE')
    def r2_in = is_paired ? "-I \"${r2}\"" : ""
    def r2_out = is_paired ? "-O '${sample_id}_clean_R2.fastq.gz'" : ""
    def sentinel_cmd = is_paired ? "" : "touch NO_FILE_R2"
    """
    set -euo pipefail

    fastp \
        -i "${r1}" ${r2_in} \
        -o '${sample_id}_clean_R1.fastq.gz' ${r2_out} \
        --json '${sample_id}_fastp.json' \
        --html '${sample_id}_fastp.html' \
        --thread ${task.cpus}

    ${sentinel_cmd}
    """
}