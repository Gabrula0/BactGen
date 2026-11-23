import hashlib
import json
import logging
import subprocess
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AnalysisRun, GenomicResult, PairwiseDistance, SequencingRun, utcnow
from app.schemas import SAMPLE_ID_PATTERN

logger = logging.getLogger("bactgen.runner")


def _extract_summary_fields(raw: dict) -> dict:
    """Extracts relevant fields from the Nextflow summary.json output."""
    qc = raw.get("qc", raw)
    mapping = raw.get("mapping_and_variants", raw)
    typing = raw.get("typing_and_amr", raw)

    return {
        "tool_versions": raw.get("tool_versions", {}),
        "qc_status": qc.get("qc_status", "WARN"),
        "raw_reads": qc.get("raw_reads"),
        "clean_reads": qc.get("clean_reads"),
        "q30_rate": qc.get("q30_rate"),
        "mean_depth": qc.get("mean_depth"),
        "genome_coverage_pct": qc.get("genome_coverage_pct"),
        "mapped_reads_pct": mapping.get("mapped_reads_pct"),
        "total_snps": mapping.get("total_snps", 0),
        "total_indels": mapping.get("total_indels", 0),
        "vcf_path": mapping.get("vcf_path"),
        "consensus_path": mapping.get("consensus_path"),
        "snp_positions": mapping.get("snp_positions", {}),
        "mlst": typing.get("mlst"),
        "mlst_alleles": typing.get("mlst_alleles", {}),
        "resistance_genes": typing.get("resistance_genes", []),
    }


def _recalculate_pairwise_distances(
    db: Session,
    current_sample_id: str,
    current_analysis_id: int,
    reference_genome: str,
    current_snps: dict,
) -> None:
    """Calculates shared SNPs and genetic distance against other samples of the same reference genome."""
    lock_id = int.from_bytes(
        hashlib.sha256(reference_genome.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

    newer_exists = (
        db.query(AnalysisRun.analysis_id)
        .join(SequencingRun, SequencingRun.run_id == AnalysisRun.run_id)
        .filter(
            SequencingRun.sample_id == current_sample_id,
            AnalysisRun.reference_genome == reference_genome,
            AnalysisRun.status == "SUCCESS",
            AnalysisRun.analysis_id > current_analysis_id,
        )
        .first()
    )
    if newer_exists:
        return

    other_rows = (
        db.query(SequencingRun.sample_id, AnalysisRun.analysis_id, GenomicResult.snp_positions)
        .join(AnalysisRun, AnalysisRun.run_id == SequencingRun.run_id)
        .join(GenomicResult, GenomicResult.analysis_id == AnalysisRun.analysis_id)
        .filter(
            AnalysisRun.status == "SUCCESS",
            AnalysisRun.reference_genome == reference_genome,
            SequencingRun.sample_id != current_sample_id,
        )
        .order_by(SequencingRun.sample_id, AnalysisRun.analysis_id.desc())
        .distinct(SequencingRun.sample_id)
        .all()
    )

    curr_dict = current_snps or {}

    for other_sample_id, other_analysis_id, other_snps in other_rows:
        other_dict = other_snps or {}
        shared_snps = sum(
            1 for pos, allele in curr_dict.items()
            if other_dict.get(pos) == allele
        )
        snp_distance = sum(
            1 for pos in (curr_dict.keys() | other_dict.keys())
            if curr_dict.get(pos) != other_dict.get(pos)
        )

        if current_sample_id < other_sample_id:
            s_a, a_a = current_sample_id, current_analysis_id
            s_b, a_b = other_sample_id, other_analysis_id
        else:
            s_a, a_a = other_sample_id, other_analysis_id
            s_b, a_b = current_sample_id, current_analysis_id

        now = utcnow()
        stmt = (
            pg_insert(PairwiseDistance)
            .values(
                sample_a_id=s_a,
                sample_b_id=s_b,
                analysis_a_id=a_a,
                analysis_b_id=a_b,
                reference_genome=reference_genome,
                snp_distance=snp_distance,
                shared_snps=shared_snps,
                calculated_at=now,
            )
            .on_conflict_do_update(
                constraint="unique_sample_ref_pair",
                set_={
                    "analysis_a_id": a_a,
                    "analysis_b_id": a_b,
                    "snp_distance": snp_distance,
                    "shared_snps": shared_snps,
                    "calculated_at": now,
                },
                where=(
                    (PairwiseDistance.analysis_a_id <= a_a)
                    & (PairwiseDistance.analysis_b_id <= a_b)
                ),
            )
        )
        db.execute(stmt)


def execute_nextflow_analysis(analysis_id: int, reference_path: str, outdir: str) -> None:
    """Task in second plane to execute Nextflow analysis for a given AnalysisRun."""
    db = SessionLocal()
    try:
        analysis = db.get(AnalysisRun, analysis_id)
        if not analysis:
            return

        seq_run = db.get(SequencingRun, analysis.run_id)
        if not seq_run:
            analysis.status = "FAILED"
            analysis.error_message = "SequencingRun asociado no encontrado."
            analysis.finished_at = utcnow()
            db.commit()
            return

        if not seq_run.sample_id or not SAMPLE_ID_PATTERN.match(seq_run.sample_id):
            analysis.status = "FAILED"
            analysis.error_message = f"Invalid sample_id format: {seq_run.sample_id!r}"
            analysis.finished_at = utcnow()
            db.commit()
            return

        analysis.status = "RUNNING"
        analysis.started_at = utcnow()
        db.commit()

        outdir_path = Path(outdir).resolve()
        outdir_path.mkdir(parents=True, exist_ok=True)
        work_path = Path(analysis.work_dir or f"work/analysis_{analysis_id}").resolve()
        log_path = Path(analysis.log_path or outdir_path / "nextflow.log").resolve()

        cmd = [
            "nextflow",
            "-log",
            str(log_path),
            "run",
            str(Path("pipeline/main.nf").resolve()),
            "-c",
            str(Path("pipeline/nextflow.config").resolve()),
            "-name",
            analysis.nextflow_run_name or f"bactgen_{analysis_id}",
            "-work-dir",
            str(work_path),
            "--sample_id",
            seq_run.sample_id,
            "--r1",
            str(Path(seq_run.fastq_r1_path).resolve()),
            "--reference",
            str(Path(reference_path).resolve()),
            "--outdir",
            str(outdir_path),
        ]
        if seq_run.fastq_r2_path:
            cmd.extend(["--r2", str(Path(seq_run.fastq_r2_path).resolve())])

        logger.info("Nextflow analysis_id=%d cmd=%s", analysis_id, " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            err_tail = (proc.stderr or proc.stdout or "Unknown error in Nextflow")[-2000:]
            analysis.status = "FAILED"
            analysis.error_message = err_tail
            analysis.finished_at = utcnow()
            db.commit()
            logger.error("Nextflow failed analysis_id=%d: %s", analysis_id, err_tail)
            return

        summary_file = outdir_path / "summary.json"
        if not summary_file.is_file():
            analysis.status = "FAILED"
            analysis.error_message = f"Nextflow terminated (0) but did not generate {summary_file}"
            analysis.finished_at = utcnow()
            db.commit()
            return

        raw_summary = json.loads(summary_file.read_text(encoding="utf-8"))
        parsed = _extract_summary_fields(raw_summary)

        result = GenomicResult(
            analysis_id=analysis.analysis_id,
            qc_status=parsed["qc_status"],
            raw_reads=parsed["raw_reads"],
            clean_reads=parsed["clean_reads"],
            q30_rate=parsed["q30_rate"],
            mean_depth=parsed["mean_depth"],
            genome_coverage_pct=parsed["genome_coverage_pct"],
            mapped_reads_pct=parsed["mapped_reads_pct"],
            total_snps=parsed["total_snps"],
            total_indels=parsed["total_indels"],
            vcf_path=parsed["vcf_path"],
            consensus_path=parsed["consensus_path"],
            snp_positions=parsed["snp_positions"],
            mlst=parsed["mlst"],
            mlst_alleles=parsed["mlst_alleles"],
            resistance_genes=parsed["resistance_genes"],
        )
        db.add(result)

        analysis.tool_versions = parsed["tool_versions"]
        analysis.status = "SUCCESS"
        analysis.finished_at = utcnow()
        db.flush()

        _recalculate_pairwise_distances(
            db=db,
            current_sample_id=seq_run.sample_id,
            current_analysis_id=analysis.analysis_id,
            reference_genome=analysis.reference_genome,
            current_snps=parsed["snp_positions"],
        )

        db.commit()
        logger.info("Nextflow analysis_id=%d completed and results ingested", analysis_id)

    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected error processing analysis_id=%d", analysis_id)
        failed_run = db.get(AnalysisRun, analysis_id)
        if failed_run:
            failed_run.status = "FAILED"
            failed_run.error_message = str(exc)[:2000]
            failed_run.finished_at = utcnow()
            db.commit()
    finally:
        db.close()