process ASSEMBLE {
    tag "$sample_id"
    publishDir "${params.outdir}/assembly", mode: 'copy', pattern: "*.contigs.fa"

    input:
    tuple val(sample_id), path(clean_r1), path(clean_r2)

    output:
    tuple val(sample_id), path("${sample_id}.contigs.fa"), emit: contigs

    script:
    def mem_bytes = task.memory ? (task.memory.toBytes() * 0.85) as long : 4_000_000_000L
    def is_paired = clean_r2 && !clean_r2.name.startsWith('NO_FILE')
    def read_args = is_paired ? "-1 ${clean_r1} -2 ${clean_r2}" : "-r ${clean_r1}"
    """
    set -euo pipefail
    megahit ${read_args} -o megahit_out -t ${task.cpus} -m ${mem_bytes} --min-contig-len 500
    cp megahit_out/final.contigs.fa ${sample_id}.contigs.fa
    """
}