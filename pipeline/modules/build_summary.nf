process BUILD_SUMMARY {
    tag "$sample_id"
    publishDir "${params.outdir}", mode: 'copy', pattern: "summary.json"

    input:
    tuple val(sample_id),
          path(fastp_json),
          path(flagstat_txt),
          path(coverage_tsv),
          path(vcf_gz),
          path(consensus_fa),
          path(mlst_tsv),
          path(amr_tsv)
    val ref_name
    val outdir_abs

    output:
    path "summary.json"

    script:
    """
    build_summary.py \
        --sample-id "${sample_id}" \
        --fastp-json "${fastp_json}" \
        --flagstat "${flagstat_txt}" \
        --coverage "${coverage_tsv}" \
        --vcf "${vcf_gz}" \
        --mlst "${mlst_tsv}" \
        --amr "${amr_tsv}" \
        --ref-name "${ref_name}" \
        --outdir-abs "${outdir_abs}"
    """
}