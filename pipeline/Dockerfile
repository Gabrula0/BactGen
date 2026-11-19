FROM mambaorg/micromamba:1.5.10

USER root
RUN micromamba install -y -n base -c conda-forge -c bioconda \
    fastp \
    minimap2 \
    samtools \
    bcftools \
    megahit \
    mlst \
    abricate \
    python=3.11 \
    && micromamba clean --all --yes

ENV PATH="/opt/conda/bin:$PATH"
RUN abricate --setupdb

RUN micromamba create -y -n mlst_env -c conda-forge -c bioconda mlst "perl>=5.32" \
    && micromamba create -y -n abricate_env -c conda-forge -c bioconda abricate perl-path-tiny \
    && PATH="/opt/conda/envs/abricate_env/bin:$PATH" /opt/conda/envs/abricate_env/bin/abricate --setupdb \
    && chmod -R a+rX /opt/conda/envs/abricate_env/db \
    && micromamba clean --all --yes \
    && printf '#!/usr/bin/env bash\nunset PERL5LIB\nexport PATH="/opt/conda/envs/mlst_env/bin:$PATH"\nexec /opt/conda/envs/mlst_env/bin/mlst "$@"\n' > /opt/conda/bin/mlst \
    && printf '#!/usr/bin/env bash\nunset PERL5LIB\nexport PATH="/opt/conda/envs/abricate_env/bin:$PATH"\nexec /opt/conda/envs/abricate_env/bin/abricate "$@"\n' > /opt/conda/bin/abricate \
    && chmod +x /opt/conda/bin/mlst /opt/conda/bin/abricate \
    && /opt/conda/bin/mlst --version \
    && /opt/conda/bin/abricate --version
