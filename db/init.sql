-- 1. Metadatos clínicos de la muestra
CREATE TABLE samples (
    sample_id        VARCHAR(50) PRIMARY KEY,
    organism         VARCHAR(100) NOT NULL,
    collection_date  DATE NOT NULL,
    hospital_ward    VARCHAR(100),
    sample_source    VARCHAR(50),  -- Ej: sangre, orina, frotis rectal
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Trazabilidad de archivos FASTQ de entrada
CREATE TABLE sequencing_runs (
    run_id           SERIAL PRIMARY KEY,
    sample_id        VARCHAR(50) NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    platform         VARCHAR(50) NOT NULL DEFAULT 'Illumina MiSeq',
    fastq_r1_path    TEXT NOT NULL,
    fastq_r2_path    TEXT,
    fastq_r1_md5     VARCHAR(32),
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Orquestación, máquina de estados y auditoría de ejecución Nextflow
CREATE TABLE analysis_runs (
    analysis_id       SERIAL PRIMARY KEY,
    run_id            INT NOT NULL REFERENCES sequencing_runs(run_id) ON DELETE CASCADE,
    pipeline_name     VARCHAR(100) NOT NULL DEFAULT 'bactgen-nf',
    pipeline_version  VARCHAR(30) NOT NULL DEFAULT '1.0.0',
    reference_genome  VARCHAR(150) NOT NULL,
    nextflow_run_name VARCHAR(100),
    status            VARCHAR(20) NOT NULL DEFAULT 'UPLOADED'
                      CHECK (status IN ('UPLOADED', 'QUEUED', 'RUNNING', 'SUCCESS', 'FAILED')),
    parameters        JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_versions     JSONB NOT NULL DEFAULT '{}'::jsonb,
    queued_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    work_dir          TEXT,
    log_path          TEXT,
    error_message     TEXT
);

-- 4. Resultados bioinformáticos (QC + Mapeo/Variantes + Tipado/AMR)
CREATE TABLE genomic_results (
    result_id           SERIAL PRIMARY KEY,
    analysis_id         INT UNIQUE NOT NULL REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE,
    -- Fase 1: QC y limpieza
    qc_status           VARCHAR(10) NOT NULL CHECK (qc_status IN ('PASS', 'WARN', 'FAIL')),
    raw_reads           BIGINT,
    clean_reads         BIGINT,
    q30_rate            NUMERIC(5,4),
    mean_depth          NUMERIC(8,2),
    genome_coverage_pct NUMERIC(5,2),
    -- Fase 2: Mapeo y Variant Calling
    mapped_reads_pct    NUMERIC(5,2),
    total_snps          INT NOT NULL DEFAULT 0,
    total_indels        INT NOT NULL DEFAULT 0,
    vcf_path            TEXT,
    consensus_path      TEXT,
    snp_positions       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Fase 3: Tipado y Resistencia Antimicrobiana (AMR)
    mlst                VARCHAR(30),
    mlst_alleles        JSONB NOT NULL DEFAULT '{}'::jsonb,
    resistance_genes    JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Distancias genéticas por parejas para vigilancia de brotes
CREATE TABLE pairwise_distances (
    distance_id       SERIAL PRIMARY KEY,
    sample_a_id       VARCHAR(50) NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    sample_b_id       VARCHAR(50) NOT NULL REFERENCES samples(sample_id) ON DELETE CASCADE,
    analysis_a_id     INT NOT NULL REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE,
    analysis_b_id     INT NOT NULL REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE,
    reference_genome  VARCHAR(150) NOT NULL,
    snp_distance      INT NOT NULL CHECK (snp_distance >= 0),
    shared_snps       INT NOT NULL DEFAULT 0,
    calculated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ordered_sample_pair CHECK (sample_a_id < sample_b_id),
    CONSTRAINT unique_sample_ref_pair UNIQUE (sample_a_id, sample_b_id, reference_genome)
);

-- Índices para consultas rápidas en la API
CREATE INDEX idx_sequencing_sample ON sequencing_runs(sample_id);
CREATE INDEX idx_analysis_status ON analysis_runs(status);
CREATE INDEX idx_analysis_reference ON analysis_runs(reference_genome);
CREATE INDEX idx_genomic_mlst ON genomic_results(mlst);
CREATE INDEX idx_genomic_genes ON genomic_results USING GIN (resistance_genes);
CREATE INDEX idx_genomic_snps ON genomic_results USING GIN (snp_positions);
CREATE INDEX idx_pairwise_distance ON pairwise_distances(snp_distance);
