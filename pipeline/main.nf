#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

include { QC_TRIM }        from './modules/qc_trim.nf'
include { MAP_AND_CALL }   from './modules/map_and_call.nf'
include { ASSEMBLE }       from './modules/assemble.nf'
include { TYPING_AND_AMR } from './modules/typing_and_amr.nf'
include { BUILD_SUMMARY }  from './modules/build_summary.nf'

workflow {
    if (!params.sample_id || !params.r1 || !params.r2 || !params.reference || !params.outdir) {
        error "Lack of required parameters: --sample_id, --r1, --r2, --reference, --outdir"
    }

    reads_ch = channel.of(
        tuple(
            params.sample_id,
            file(params.r1, checkIfExists: true),
            file(params.r2, checkIfExists: true)
        )
    )
    ref_file = file(params.reference, checkIfExists: true)

    QC_TRIM(reads_ch)
    MAP_AND_CALL(QC_TRIM.out.reads, ref_file)
    ASSEMBLE(QC_TRIM.out.reads)
    TYPING_AND_AMR(ASSEMBLE.out.contigs)

    summary_input = QC_TRIM.out.json
        .join(MAP_AND_CALL.out.stats_and_vcf)
        .join(TYPING_AND_AMR.out.reports)

    BUILD_SUMMARY(summary_input, ref_file.getName(), params.outdir)
}
