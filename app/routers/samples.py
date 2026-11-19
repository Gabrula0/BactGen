import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Sample, SequencingRun
from app.schemas import SampleCreate, SampleResponse, SequencingRunCreate, SequencingRunResponse

router = APIRouter(prefix="/samples", tags=["Samples & Sequencing"])


def _compute_md5(file_path: Path) -> str:
    md5 = hashlib.md5()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            md5.update(chunk)
    return md5.hexdigest()


@router.post("", response_model=SampleResponse, status_code=status.HTTP_201_CREATED)
def create_sample(payload: SampleCreate, db: Session = Depends(get_db)):
    if db.get(Sample, payload.sample_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sample '{payload.sample_id}' is already registered.",
        )
    sample = Sample(**payload.model_dump())
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


@router.get("", response_model=list[SampleResponse])
def list_samples(
    ward: str | None = None,
    organism: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(Sample)
    if ward:
        query = query.filter(Sample.hospital_ward == ward)
    if organism:
        query = query.filter(Sample.organism.ilike(f"%{organism}%"))
    return query.order_by(Sample.created_at.desc()).limit(limit).all()


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(sample_id: str, db: Session = Depends(get_db)):
    sample = db.get(Sample, sample_id)
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample '{sample_id}' not found.",
        )
    return sample


@router.post(
    "/{sample_id}/sequencing-runs",
    response_model=SequencingRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def attach_sequencing_run(
    sample_id: str,
    payload: SequencingRunCreate,
    db: Session = Depends(get_db),
):
    if not db.get(Sample, sample_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample '{sample_id}' not found.",
        )

    r1 = Path(payload.fastq_r1_path)
    if not r1.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File R1 not found on disk: {payload.fastq_r1_path}",
        )

    if payload.fastq_r2_path and not Path(payload.fastq_r2_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File R2 not found on disk: {payload.fastq_r2_path}",
        )

    seq_run = SequencingRun(
        sample_id=sample_id,
        platform=payload.platform,
        fastq_r1_path=payload.fastq_r1_path,
        fastq_r2_path=payload.fastq_r2_path,
        fastq_r1_md5=payload.fastq_r1_md5 or _compute_md5(r1),
    )
    db.add(seq_run)
    db.commit()
    db.refresh(seq_run)
    return seq_run
