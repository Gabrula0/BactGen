process TYPING_AND_AMR {
    tag "$sample_id"
    publishDir "${params.outdir}/typing", mode: 'copy', pattern: "*.{mlst.tsv,amr.tsv}"

    input:
    tuple val(sample_id), path(contigs)

    output:
    tuple val(sample_id), path("${sample_id}.mlst.tsv"), path("${sample_id}.amr.tsv"), emit: reports

    script:
    """
    set -euo pipefail

    mlst "${contigs}" > "${sample_id}.mlst.tsv"
    abricate --db ncbi "${contigs}" > "${sample_id}.amr.tsv"
    """
}