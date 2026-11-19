from collections import defaultdict, deque
from datetime import date
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnalysisRun, PairwiseDistance, Sample, SequencingRun
from app.schemas import (
    AnalysisCreate,
    AnalysisRunResponse,
    GenomicResultResponse,
    PairwiseDistanceResponse,
)
from app.services.pipeline_runner import execute_nextflow_analysis

router = APIRouter(tags=["Analyses & Outbreak Surveillance"])


class ClusterMember(BaseModel):
    sample_id: str
    hospital_ward: str | None
    collection_date: date | None
    sample_source: str | None


class OutbreakCluster(BaseModel):
    cluster_id: int
    size: int
    reference_genome: str
    members: list[ClusterMember]
    links: list[PairwiseDistanceResponse]


class ClustersResponse(BaseModel):
    threshold_snps: int
    total_clusters: int
    clusters: list[OutbreakCluster]


def _queue_analysis(
    payload: AnalysisCreate,
    background_tasks: BackgroundTasks,
    db: Session,
) -> AnalysisRun:
    seq_run = db.get(SequencingRun, payload.run_id)
    if not seq_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SequencingRun run_id={payload.run_id} no encontrado.",
        )

    ref_file = Path(payload.reference_path)
    if not ref_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Genoma de referencia no encontrado en disco: {payload.reference_path}",
        )

    nf_run_name = f"bactgen_{seq_run.sample_id}_{uuid.uuid4().hex[:8]}"
    analysis = AnalysisRun(
        run_id=seq_run.run_id,
        reference_genome=ref_file.name,
        nextflow_run_name=nf_run_name,
        status="QUEUED",
        parameters=payload.parameters,
    )
    db.add(analysis)
    db.flush()

    outdir = f"data/runs/{seq_run.sample_id}/analysis_{analysis.analysis_id}"
    analysis.work_dir = f"work/analysis_{analysis.analysis_id}"
    analysis.log_path = f"{outdir}/nextflow.log"
    db.commit()
    db.refresh(analysis)

    background_tasks.add_task(
        execute_nextflow_analysis,
        analysis_id=analysis.analysis_id,
        reference_path=str(ref_file),
        outdir=outdir,
    )
    return analysis


@router.post("/analysis", response_model=AnalysisRunResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_analysis_singular(
    payload: AnalysisCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return _queue_analysis(payload, background_tasks, db)


@router.post("/analyses", response_model=AnalysisRunResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_analysis(
    payload: AnalysisCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return _queue_analysis(payload, background_tasks, db)


@router.get("/analyses/{analysis_id}", response_model=AnalysisRunResponse)
def get_analysis_status(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.get(AnalysisRun, analysis_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Análisis analysis_id={analysis_id} no encontrado.",
        )
    return analysis


@router.get("/analyses/{analysis_id}/results", response_model=GenomicResultResponse)
def get_analysis_results(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.get(AnalysisRun, analysis_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Análisis analysis_id={analysis_id} no encontrado.",
        )
    if analysis.status != "SUCCESS" or not analysis.genomic_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resultados aún no disponibles (estado actual: {analysis.status}).",
        )
    return analysis.genomic_result


@router.get("/outbreaks/distances", response_model=list[PairwiseDistanceResponse])
def list_pairwise_distances(
    max_snps: int = Query(default=20, ge=0),
    reference_genome: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PairwiseDistance).filter(PairwiseDistance.snp_distance <= max_snps)
    if reference_genome:
        query = query.filter(PairwiseDistance.reference_genome == reference_genome)
    return query.order_by(PairwiseDistance.snp_distance.asc()).all()


@router.get("/clusters", response_model=ClustersResponse)
def detect_outbreak_clusters(
    max_snps: int = Query(default=20, ge=0, description="Umbral máximo de SNPs para agrupar muestras en un clúster"),
    reference_genome: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(PairwiseDistance).filter(PairwiseDistance.snp_distance <= max_snps)
    if reference_genome:
        query = query.filter(PairwiseDistance.reference_genome == reference_genome)

    edges = query.order_by(PairwiseDistance.snp_distance.asc()).all()
    if not edges:
        return ClustersResponse(threshold_snps=max_snps, total_clusters=0, clusters=[])

    edges_by_ref: dict[str, list[PairwiseDistance]] = defaultdict(list)
    all_sample_ids: set[str] = set()
    for edge in edges:
        edges_by_ref[edge.reference_genome].append(edge)
        all_sample_ids.add(edge.sample_a_id)
        all_sample_ids.add(edge.sample_b_id)

    samples_map = {
        s.sample_id: s
        for s in db.query(Sample).filter(Sample.sample_id.in_(all_sample_ids)).all()
    }

    clusters: list[OutbreakCluster] = []
    cluster_idx = 1

    for ref, ref_edges in edges_by_ref.items():
        adj: dict[str, set[str]] = defaultdict(set)
        for e in ref_edges:
            adj[e.sample_a_id].add(e.sample_b_id)
            adj[e.sample_b_id].add(e.sample_a_id)

        visited: set[str] = set()
        for node in sorted(adj.keys()):
            if node in visited:
                continue
            component: list[str] = []
            queue = deque([node])
            visited.add(node)
            while queue:
                curr = queue.popleft()
                component.append(curr)
                for neighbor in sorted(adj[curr]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            component_set = set(component)
            component_edges = [
                PairwiseDistanceResponse.model_validate(e)
                for e in ref_edges
                if e.sample_a_id in component_set and e.sample_b_id in component_set
            ]
            members = [
                ClusterMember(
                    sample_id=sid,
                    hospital_ward=samples_map[sid].hospital_ward if sid in samples_map else None,
                    collection_date=samples_map[sid].collection_date if sid in samples_map else None,
                    sample_source=samples_map[sid].sample_source if sid in samples_map else None,
                )
                for sid in sorted(component)
            ]
            clusters.append(
                OutbreakCluster(
                    cluster_id=cluster_idx,
                    size=len(members),
                    reference_genome=ref,
                    members=members,
                    links=component_edges,
                )
            )
            cluster_idx += 1

    return ClustersResponse(
        threshold_snps=max_snps,
        total_clusters=len(clusters),
        clusters=clusters,
    )
