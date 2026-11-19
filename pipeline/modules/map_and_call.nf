process MAP_AND_CALL {
    tag "$sample_id"
    publishDir "${params.outdir}/variants", mode: 'copy', pattern: "*.{vcf.gz,vcf.gz.tbi,consensus.fa,coverage.tsv}"

    input:
    tuple val(sample_id), path(clean_r1), path(clean_r2)
    path reference

    output:
    tuple val(sample_id),
          path("${sample_id}.flagstat.txt"),
          path("${sample_id}.coverage.tsv"),
          path("${sample_id}.filtered.vcf.gz"),
          path("${sample_id}.consensus.fa"), emit: stats_and_vcf
    path "${sample_id}.filtered.vcf.gz.tbi"

    script:
    """
    minimap2 -ax sr -t ${task.cpus} ${reference} ${clean_r1} ${clean_r2} \
        | samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam

    samtools index ${sample_id}.sorted.bam
    samtools flagstat ${sample_id}.sorted.bam > ${sample_id}.flagstat.txt
    samtools coverage ${sample_id}.sorted.bam > ${sample_id}.coverage.tsv

    bcftools mpileup -Ou -f ${reference} --max-depth 500 ${sample_id}.sorted.bam \
        | bcftools call --ploidy 1 -mv -Oz -o ${sample_id}.raw.vcf.gz

    bcftools filter -i "QUAL>=${params.min_qual} && INFO/DP>=${params.min_depth}" \
        ${sample_id}.raw.vcf.gz -Oz -o ${sample_id}.filtered.vcf.gz

    bcftools index -t ${sample_id}.filtered.vcf.gz
    bcftools consensus -f ${reference} ${sample_id}.filtered.vcf.gz > ${sample_id}.consensus.fa
    """
}
