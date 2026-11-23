process ASSEMBLE {
    tag "$sample_id"
    publishDir "${params.outdir}/assembly", mode: 'copy', pattern: "*.contigs.fa"

    input:
    tuple val(sample_id), path(clean_r1), path(clean_r2)

    output:
    tuple val(sample_id), path("${sample_id}.contigs.fa"), emit: contigs

    script:
    """
    megahit -1 ${clean_r1} -2 ${clean_r2} -o megahit_out -t ${task.cpus} --min-contig-len 500
    cp megahit_out/final.contigs.fa ${sample_id}.contigs.fa
    """
}
