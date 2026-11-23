process MAP_AND_CALL {
    tag "$sample_id"
    publishDir "${params.outdir}/variants", mode: 'copy', pattern: "*.{vcf.gz,vcf.gz.tbi,consensus.fa,coverage.tsv}"

    input:
    tuple val(sample_id), path(clean_reads)
    path reference

    output:
    tuple val(sample_id),
          path("${sample_id}.flagstat.txt"),
          path("${sample_id}.coverage.tsv"),
          path("${sample_id}.filtered.vcf.gz"),
          path("${sample_id}.consensus.fa"), emit: stats_and_vcf
    path "${sample_id}.filtered.vcf.gz.tbi"

    script:
    def reads_list = (clean_reads instanceof List ? clean_reads : [clean_reads]).findAll { !it.name.startsWith('NO_FILE') }
    def reads_arg = reads_list.collect { "\"${it}\"" }.join(' ')
    """
    set -euo pipefail

    minimap2 -ax sr -t ${task.cpus} "${reference}" ${reads_arg} \
        | samtools sort -@ ${task.cpus} -o "${sample_id}.sorted.bam"

    samtools index "${sample_id}.sorted.bam"
    samtools flagstat "${sample_id}.sorted.bam" > "${sample_id}.flagstat.txt"
    samtools coverage "${sample_id}.sorted.bam" > "${sample_id}.coverage.tsv"

    samtools depth -aa "${sample_id}.sorted.bam" \
        | awk -v min_dp="${params.min_depth}" '
            BEGIN { OFS="\\t"; chr=""; start=-1; end=-1 }
            \$3 < min_dp {
                if (\$1 == chr && \$2 - 1 == end) {
                    end = \$2
                } else {
                    if (chr != "") print chr, start, end
                    chr = \$1
                    start = \$2 - 1
                    end = \$2
                }
            }
            END { if (chr != "") print chr, start, end }
        ' > "${sample_id}.low_cov.bed"

    bcftools mpileup -Ou -f "${reference}" --max-depth 500 "${sample_id}.sorted.bam" \
        | bcftools call --ploidy 1 -mv -Oz -o "${sample_id}.raw.vcf.gz"

    bcftools filter -i "QUAL>=${params.min_qual} && INFO/DP>=${params.min_depth}" \
        "${sample_id}.raw.vcf.gz" -Oz -o "${sample_id}.filtered.vcf.gz"

    bcftools index -t "${sample_id}.filtered.vcf.gz"
    bcftools consensus -f "${reference}" --mask "${sample_id}.low_cov.bed" \
        "${sample_id}.filtered.vcf.gz" > "${sample_id}.consensus.fa"
    """
}