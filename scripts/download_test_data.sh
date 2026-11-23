#!/usr/bin/env bash
set -euo pipefail

python3 - << 'PYEOF'
import os
import urllib.parse
import urllib.request

ref_path = "data/reference/S_aureus_NCTC8325.fasta"
if not os.path.exists(ref_path):
    print("Descargando genoma de referencia (S. aureus NCTC 8325 - CP000253.1)...")
    ref_url = "https://www.ebi.ac.uk/ena/browser/api/fasta/CP000253.1?download=true"
    urllib.request.urlretrieve(ref_url, ref_path)
    print(f" -> Guardado en {ref_path}")

params = urllib.parse.urlencode({
    "result": "read_run",
    "query": 'tax_id=1280 AND library_strategy="WGS" AND library_layout="PAIRED" AND instrument_platform="ILLUMINA" AND base_count>90000000 AND base_count<210000000',
    "fields": "run_accession,study_accession,fastq_ftp",
    "limit": "6",
    "format": "tsv"
})

api_url = f"https://www.ebi.ac.uk/ena/portal/api/search?{params}"
lines = urllib.request.urlopen(api_url).read().decode().strip().splitlines()

print(f"\nDescargando {len(lines)-1} muestras paired-end desde ENA...")
for line in lines[1:]:
    acc, study, ftps = line.split("\t")
    for ftp_path in ftps.split(";"):
        if ftp_path:
            fname = os.path.basename(ftp_path)
            dest = os.path.join("data/fastq", fname)
            if not os.path.exists(dest):
                print(f" -> {fname} (BioProject: {study})")
                urllib.request.urlretrieve(f"https://{ftp_path}", dest)

print("\nDescarga completada.")
PYEOF

ls -lh data/reference/ data/fastq/
