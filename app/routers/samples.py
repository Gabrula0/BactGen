import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Sample, SequencingRun
from app.schemas import SampleCreate, SampleResponse, SequencingRunCreate, SequencingRunResponse

router = APIRouter(prefix="/samples", tags=["Samples & Sequencing"])

FASTQ_DIR = Path("data/fastq")
ALLOWED_EXTS = (".fastq.gz", ".fq.gz", ".fastq", ".fq")


def _compute_md5(file_path: Path) -> str:
    md5 = hashlib.md5()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            md5.update(chunk)
    return md5.hexdigest()


async def _stream_to_disk(upload: UploadFile, dest_dir: Path) -> tuple[str, str]:
    filename = Path(upload.filename or "").name
    if not filename.lower().endswith(ALLOWED_EXTS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file format ({filename}). Use .fastq.gz or .fq.gz files.",
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    md5 = hashlib.md5()

    with dest_path.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            out.write(chunk)
            md5.update(chunk)

    return dest_path.as_posix(), md5.hexdigest()


@router.get("/available-fastq", response_model=list[str])
def list_available_fastq():
    if not FASTQ_DIR.is_dir():
        return []
    return [
        p.as_posix()
        for p in sorted(FASTQ_DIR.iterdir())
        if p.is_file() and p.name.lower().endswith(ALLOWED_EXTS)
    ]


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


@router.get("/{sample_id}/sequencing-runs", response_model=list[SequencingRunResponse])
def list_sample_sequencing_runs(sample_id: str, db: Session = Depends(get_db)):
    if not db.get(Sample, sample_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample '{sample_id}' not found.",
        )
    return (
        db.query(SequencingRun)
        .filter(SequencingRun.sample_id == sample_id)
        .order_by(SequencingRun.uploaded_at.desc())
        .all()
    )


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
            detail=f"R1 file not found on disk: {payload.fastq_r1_path}",
        )

    if payload.fastq_r2_path and not Path(payload.fastq_r2_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"R2 file not found on disk: {payload.fastq_r2_path}",
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


@router.post(
    "/{sample_id}/sequencing-runs/upload",
    response_model=SequencingRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_sequencing_run(
    sample_id: str,
    platform: str = Form("Illumina MiSeq"),
    r1_file: UploadFile = File(...),
    r2_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if not db.get(Sample, sample_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample '{sample_id}' not found.",
        )

    r1_path, r1_md5 = await _stream_to_disk(r1_file, FASTQ_DIR)
    r2_path = None
    if r2_file and r2_file.filename:
        r2_path, _ = await _stream_to_disk(r2_file, FASTQ_DIR)

    seq_run = SequencingRun(
        sample_id=sample_id,
        platform=platform,
        fastq_r1_path=r1_path,
        fastq_r2_path=r2_path,
        fastq_r1_md5=r1_md5,
    )
    db.add(seq_run)
    db.commit()
    db.refresh(seq_run)
    return seq_run
