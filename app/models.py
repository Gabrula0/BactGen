from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sample(Base):
    __tablename__ = "samples"

    sample_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    organism: Mapped[str] = mapped_column(String(100), nullable=False)
    collection_date: Mapped[date] = mapped_column(Date, nullable=False)
    hospital_ward: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sample_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    sequencing_runs: Mapped[list["SequencingRun"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class SequencingRun(Base):
    __tablename__ = "sequencing_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("samples.sample_id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), default="Illumina MiSeq", nullable=False)
    fastq_r1_path: Mapped[str] = mapped_column(Text, nullable=False)
    fastq_r2_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    fastq_r1_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    sample: Mapped["Sample"] = relationship(back_populates="sequencing_runs")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="sequencing_run", cascade="all, delete-orphan"
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('UPLOADED', 'QUEUED', 'RUNNING', 'SUCCESS', 'FAILED')",
            name="analysis_runs_status_check",
        ),
    )

    analysis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sequencing_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    pipeline_name: Mapped[str] = mapped_column(String(100), default="bactgen-nf", nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(30), default="1.0.0", nullable=False)
    reference_genome: Mapped[str] = mapped_column(String(150), nullable=False)
    nextflow_run_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED", nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tool_versions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    work_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sequencing_run: Mapped["SequencingRun"] = relationship(back_populates="analysis_runs")
    genomic_result: Mapped["GenomicResult | None"] = relationship(
        back_populates="analysis_run", uselist=False, cascade="all, delete-orphan"
    )


class GenomicResult(Base):
    __tablename__ = "genomic_results"
    __table_args__ = (
        CheckConstraint("qc_status IN ('PASS', 'WARN', 'FAIL')", name="genomic_results_qc_status_check"),
    )

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.analysis_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    qc_status: Mapped[str] = mapped_column(String(10), nullable=False)
    raw_reads: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    clean_reads: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    q30_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    mean_depth: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    genome_coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    mapped_reads_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_snps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_indels: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vcf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    consensus_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snp_positions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    mlst: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mlst_alleles: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    resistance_genes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="genomic_result")


class PairwiseDistance(Base):
    __tablename__ = "pairwise_distances"
    __table_args__ = (
        CheckConstraint("snp_distance >= 0", name="pairwise_distances_snp_distance_check"),
        CheckConstraint("sample_a_id < sample_b_id", name="ordered_sample_pair"),
        UniqueConstraint("sample_a_id", "sample_b_id", "reference_genome", name="unique_sample_ref_pair"),
    )

    distance_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_a_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("samples.sample_id", ondelete="CASCADE"), nullable=False
    )
    sample_b_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("samples.sample_id", ondelete="CASCADE"), nullable=False
    )
    analysis_a_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.analysis_id", ondelete="CASCADE"), nullable=False
    )
    analysis_b_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.analysis_id", ondelete="CASCADE"), nullable=False
    )
    reference_genome: Mapped[str] = mapped_column(String(150), nullable=False)
    snp_distance: Mapped[int] = mapped_column(Integer, nullable=False)
    shared_snps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
