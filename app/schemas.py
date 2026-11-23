import re
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

SAMPLE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,49}$")


# --- Samples & Sequencing Runs ---
class SampleCreate(BaseModel):
    sample_id: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=SAMPLE_ID_PATTERN.pattern,
        examples=["DRR107085"],
    )
    organism: str = Field(default="Staphylococcus aureus", max_length=100)
    collection_date: date = Field(..., examples=["2026-11-19"])
    hospital_ward: str | None = Field(None, max_length=100, examples=["UCI-Adultos"])
    sample_source: str | None = Field(None, max_length=50, examples=["blood"])

    @field_validator("sample_id")
    @classmethod
    def validate_sample_id(cls, value: str) -> str:
        if not SAMPLE_ID_PATTERN.match(value):
            raise ValueError(
                "sample_id must be 2-50 characters, start with an alphanumeric character, "
                "and contain only letters, numbers, '.', '_' or '-'."
            )
        return value


class SampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    organism: str
    collection_date: date
    hospital_ward: str | None
    sample_source: str | None
    created_at: datetime


class SequencingRunCreate(BaseModel):
    platform: str = Field(default="Illumina MiSeq", max_length=50)
    fastq_r1_path: str = Field(..., examples=["data/fastq/DRR107085_1.fastq.gz"])
    fastq_r2_path: str | None = Field(None, examples=["data/fastq/DRR107085_2.fastq.gz"])
    fastq_r1_md5: str | None = Field(None, min_length=32, max_length=32)


class SequencingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    sample_id: str
    platform: str
    fastq_r1_path: str
    fastq_r2_path: str | None
    fastq_r1_md5: str | None
    uploaded_at: datetime


# --- Analysis Runs & Genomic Results ---
class AnalysisCreate(BaseModel):
    run_id: int = Field(..., gt=0)
    reference_path: str = Field(
        default="data/reference/S_aureus_NCTC8325.fasta",
        examples=["data/reference/S_aureus_NCTC8325.fasta"],
    )
    parameters: dict = Field(default_factory=dict)


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    run_id: int
    pipeline_name: str
    pipeline_version: str
    reference_genome: str
    nextflow_run_name: str | None
    status: Literal["UPLOADED", "QUEUED", "RUNNING", "SUCCESS", "FAILED"]
    parameters: dict
    tool_versions: dict
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    work_dir: str | None
    log_path: str | None
    error_message: str | None


class GenomicResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    analysis_id: int
    qc_status: str
    raw_reads: int | None
    clean_reads: int | None
    q30_rate: float | None
    mean_depth: float | None
    genome_coverage_pct: float | None
    mapped_reads_pct: float | None
    total_snps: int
    total_indels: int
    vcf_path: str | None
    consensus_path: str | None
    mlst: str | None
    mlst_alleles: dict
    resistance_genes: list
    created_at: datetime


class PairwiseDistanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distance_id: int
    sample_a_id: str
    sample_b_id: str
    analysis_a_id: int
    analysis_b_id: int
    reference_genome: str
    snp_distance: int
    shared_snps: int
    calculated_at: datetime