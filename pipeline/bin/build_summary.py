#!/usr/bin/env python3
import argparse
import gzip
import json
import os
import re
import subprocess


def get_ver(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out.strip().splitlines()[0]
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Consolidate BactGen pipeline outputs into summary.json")
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--fastp-json", required=True)
    parser.add_argument("--flagstat", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--vcf", required=True)
    parser.add_argument("--mlst", required=True)
    parser.add_argument("--amr", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--outdir-abs", required=True)
    args = parser.parse_args()

    tool_versions = {
        "fastp": get_ver(["fastp", "--version"]),
        "minimap2": get_ver(["minimap2", "--version"]),
        "samtools": get_ver(["samtools", "--version"]),
        "bcftools": get_ver(["bcftools", "--version"]),
        "megahit": get_ver(["megahit", "--version"]),
        "mlst": get_ver(["mlst", "--version"]),
        "abricate": get_ver(["abricate", "--version"]),
    }

    # 1. Parse fastp QC
    with open(args.fastp_json) as f:
        fp = json.load(f)
    raw_reads = int(fp["summary"]["before_filtering"]["total_reads"])
    clean_reads = int(fp["summary"]["after_filtering"]["total_reads"])
    q30_rate = round(float(fp["summary"]["after_filtering"]["q30_rate"]), 4)

    # 2. Parse samtools flagstat
    mapped_pct = 0.0
    with open(args.flagstat) as f:
        for line in f:
            if "mapped (" in line and "primary mapped" not in line:
                m = re.search(r"\(([0-9.]+)%", line)
                if m:
                    mapped_pct = round(float(m.group(1)), 2)
                break

    # 3. Parse samtools coverage
    total_len = 0
    total_cov_bases = 0
    weighted_depth_sum = 0.0
    with open(args.coverage) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            length = int(parts[2]) - int(parts[1]) + 1
            cov_bases = int(parts[4])
            mean_d = float(parts[6])
            total_len += length
            total_cov_bases += cov_bases
            weighted_depth_sum += mean_d * length

    genome_coverage_pct = round((total_cov_bases / total_len * 100.0), 2) if total_len > 0 else 0.0
    mean_depth = round((weighted_depth_sum / total_len), 2) if total_len > 0 else 0.0

    if mean_depth >= 20.0 and genome_coverage_pct >= 90.0 and q30_rate >= 0.75:
        qc_status = "PASS"
    elif mean_depth >= 10.0 and genome_coverage_pct >= 80.0:
        qc_status = "WARN"
    else:
        qc_status = "FAIL"

    # 4. Parse filtered VCF (SNPs, INDELs & exact SNP map)
    total_snps = 0
    total_indels = 0
    snp_positions = {}
    with gzip.open(args.vcf, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            chrom, pos, _, ref, alt = parts[0], parts[1], parts[2], parts[3], parts[4]
            alt_allele = alt.split(",")[0]
            if len(ref) == 1 and len(alt_allele) == 1:
                total_snps += 1
                snp_positions[f"{chrom}:{pos}"] = f"{ref}>{alt_allele}"
            else:
                total_indels += 1

    # 5. Parse MLST
    mlst_st = "ND"
    mlst_alleles = {}
    with open(args.mlst) as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                raw_st = parts[2]
                mlst_st = f"ST{raw_st}" if raw_st.isdigit() else raw_st
                for allele in parts[3:]:
                    if "(" in allele and allele.endswith(")"):
                        locus, val = allele[:-1].split("(", 1)
                        mlst_alleles[locus] = val

    # 6. Parse ABRicate AMR genes
    resistance_genes = []
    with open(args.amr) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 14:
                resistance_genes.append({
                    "gene": parts[5],
                    "coverage_pct": float(parts[9]),
                    "identity_pct": float(parts[10]),
                    "database": parts[11],
                    "accession": parts[12],
                    "product": parts[13],
                    "resistance": parts[14] if len(parts) > 14 else ""
                })

    summary = {
        "sample_id": args.sample_id,
        "reference_genome": args.ref_name,
        "tool_versions": tool_versions,
        "qc": {
            "qc_status": qc_status,
            "raw_reads": raw_reads,
            "clean_reads": clean_reads,
            "q30_rate": q30_rate,
            "mean_depth": mean_depth,
            "genome_coverage_pct": genome_coverage_pct
        },
        "mapping_and_variants": {
            "mapped_reads_pct": mapped_pct,
            "total_snps": total_snps,
            "total_indels": total_indels,
            "vcf_path": os.path.join(args.outdir_abs, "variants", f"{args.sample_id}.filtered.vcf.gz"),
            "consensus_path": os.path.join(args.outdir_abs, "variants", f"{args.sample_id}.consensus.fa"),
            "snp_positions": snp_positions
        },
        "typing_and_amr": {
            "mlst": mlst_st,
            "mlst_alleles": mlst_alleles,
            "resistance_genes": resistance_genes
        }
    }

    with open("summary.json", "w") as out:
        json.dump(summary, out, indent=2)


if __name__ == "__main__":
    main()
