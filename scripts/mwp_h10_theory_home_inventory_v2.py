#!/usr/bin/env python3
"""Build H10 v2 TheoryHomeRecords from EFC package metadata, read-only."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2] / "symbiose-workspace" / "EFC"
PACKAGES = REPO / "docs" / "papers" / "efc"
PUBLIC = REPO / "docs" / "public"
OUT = Path(__file__).resolve().parents[1] / "docs" / "mwp-h10-theory-home-inventory-v2.json"

LANES = {
    "H10.2": "Ontology & foundations",
    "H10.3": "Physical EFC model & cosmology",
    "H10.4": "EBE & regime architecture",
    "H10.5": "Measurement & comparison methodology",
    "H10.6": "Empirical validation, predictions & falsification",
    "H10.7": "Consciousness, cognition & meta-models",
    "H10.8": "Symbiosis & structural intelligence",
    "H10.10": "Computational pipelines & reproducibility",
}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def text_for(package: str, readme: str, meta: dict[str, Any]) -> str:
    return " ".join([
        package,
        readme,
        str(meta.get("title", "")),
        str(meta.get("paper_type", "")),
        str(meta.get("type", "")),
        str(meta.get("keywords", "")),
        str(meta.get("description", "")),
        str(meta.get("layer", "")),
    ]).lower()


def classify_lane(package: str, readme: str, meta: dict[str, Any], has_source: bool, has_data: bool) -> tuple[str | None, str]:
    hay = text_for(package, readme, meta)
    name = package.lower()
    # Explicit package identity outranks incidental words in long abstracts.
    if any(x in name for x in ("symbiosis", "validity-aware-ai", "co-reflection", "structural-intelligence")):
        return "H10.8", "explicit package-name Symbiosis/AI architecture match"
    if any(x in name for x in ("ebe", "l0–l3", "l0-l3", "regime-architecture", "regime_architecture")):
        return "H10.4", "explicit package-name EBE/regime match"
    if any(x in name for x in ("rcmp", "regime-consistent-measurement", "regime_consistent_measurement")):
        return "H10.5", "explicit package-name RCMP/methodology match"
    if any(x in name for x in ("consciousness", "cognitive", "autopoiesis", "homo_fluxus", "homo-fluxus", "cem-")):
        return "H10.7", "explicit package-name consciousness/cognition match"
    if any(x in hay for x in ("consciousness", "cognitive", "autopoiesis", "homo fluxus", "cem-", "cognitive entropy")):
        return "H10.7", "metadata cognitive/consciousness match"
    if any(x in hay for x in ("symbiosis", "human-ai", "validity-aware-ai", "co-reflection", "structural intelligence")):
        return "H10.8", "metadata Symbiosis/AI architecture match"
    if any(x in hay for x in ("rcmp", "regime-consistent measurement", "measurement principle", "likelihood", "model comparison", "regime-locked measurement")):
        return "H10.5", "metadata measurement/methodology match"
    if any(x in hay for x in ("entropy-bounded", "ebe", "l0–l3", "l0-l3", "regime architecture", "regime transition")):
        return "H10.4", "metadata EBE/regime match"
    if any(x in hay for x in ("validation", "prediction", "kill-test", "empirical", "prereg", "statistical analysis", "observational")):
        return "H10.6", "index/type/tier validation match"
    if has_source or has_data:
        return "H10.10", "package contains source/data implementation surface"
    if any(x in hay for x in ("ontology", "foundations", "formal spec", "core principles")):
        return "H10.2", "metadata ontology/foundations match"
    if any(x in hay for x in ("efc", "cosmolog", "gravit", "entropy", "energy flow", "field equation")):
        return "H10.3", "metadata physical EFC match"
    return None, "insufficient authoritative metadata"


def classify_claim(meta: dict[str, Any], lane_id: str | None) -> tuple[str, str]:
    status = str(meta.get("status", "")).lower()
    paper_type = str(meta.get("paper_type", meta.get("type", ""))).lower()
    tier = str(meta.get("tier", "")).upper()
    sealed = meta.get("sealed_predictions")
    kill = meta.get("kill_criteria")
    if any(x in paper_type for x in ("empirical", "validation", "statistical", "observational", "post-hoc")):
        return ("EVIDENCE_INTERNAL" if status == "published" else "VALIDATION_PENDING", "index paper_type/status")
    if "prediction" in paper_type or bool(sealed) or (tier == "T3" and any(x in paper_type for x in ("forecast", "prediction", "prereg", "sealed"))):
        return ("PREDICTION_SEALED", "index prediction/tier/sealed metadata")
    if "method" in paper_type or lane_id == "H10.5":
        return ("METHODOLOGY", "index paper_type/lane")
    if lane_id in {"H10.2", "H10.3", "H10.4"}:
        return ("MODEL_EQUATION" if meta.get("core_equations") else "ONTOLOGY", "index lane/core_equations")
    if lane_id in {"H10.7", "H10.8"}:
        return ("HYPOTHESIS", "meta/cognition/AI lane requires claim review")
    if kill:
        return ("VALIDATION_PENDING", "kill_criteria present; outcome not inferred")
    return ("UNCLASSIFIED", "no safe claim classification")


def main() -> None:
    rows: list[dict[str, Any]] = []
    for readme in sorted(PACKAGES.rglob("README.md")):
        package_dir = readme.parent
        rel_dir = package_dir.relative_to(PACKAGES)
        if not rel_dir.parts or rel_dir.parts == ("_archived",):
            continue
        try:
            readme_text = readme.read_text(encoding="utf-8", errors="ignore")[:30000]
        except OSError:
            readme_text = ""
        meta = load_json(package_dir / "index.json") or {}
        lane_id, basis = classify_lane(str(rel_dir), readme_text, meta, (package_dir / "src").is_dir(), (package_dir / "data").is_dir())
        lane_name = LANES.get(lane_id) if lane_id else None
        claim_status, claim_basis = classify_claim(meta, lane_id)
        doi = meta.get("doi")
        if not doi:
            m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", readme_text, re.I)
            doi = m.group(0) if m else None
        public_refs = []
        for public_file in PUBLIC.glob("*"):
            if public_file.is_file() and public_file.suffix.lower() in {".html", ".md", ".json"}:
                try:
                    if package_dir.name in public_file.read_text(encoding="utf-8", errors="ignore"):
                        public_refs.append(str(public_file.relative_to(REPO)))
                except OSError:
                    pass
        rows.append({
            "package_id": str(rel_dir),
            "readme": str(readme.relative_to(REPO)),
            "index_json": str((package_dir / "index.json").relative_to(REPO)) if (package_dir / "index.json").exists() else None,
            "title": meta.get("title"), "doi": doi, "paper_type": meta.get("paper_type", meta.get("type")),
            "status_source": meta.get("status"), "tier": meta.get("tier"),
            "lane_id": lane_id, "lane_name": lane_name, "lane_basis": basis,
            "claim_status": claim_status, "claim_basis": claim_basis,
            "has_schema": any(package_dir.glob("**/*schema*.json")),
            "has_data": (package_dir / "data").is_dir(), "has_source": (package_dir / "src").is_dir(),
            "has_pdf": any(package_dir.glob("*.pdf")), "public_refs": public_refs[:20],
            "source_layer": "paper_package", "steward": "efc-asi-steward (PROPOSED_NOT_LIVE_VERIFIED)",
            "graph_projection_status": "NOT_PROBED", "readback_status": "DECLARED_METADATA_CLASSIFICATION",
        })
    counts: dict[str, int] = {"records": len(rows), "public_files": len(list(PUBLIC.glob("*")))}
    for key in ("lane_id", "claim_status"):
        counts[key] = len({r[key] for r in rows if r[key]})
    lane_counts: dict[str, int] = {}
    claim_counts: dict[str, int] = {}
    for r in rows:
        lane_counts[r["lane_id"] or "UNMAPPED"] = lane_counts.get(r["lane_id"] or "UNMAPPED", 0) + 1
        claim_counts[r["claim_status"]] = claim_counts.get(r["claim_status"], 0) + 1
    out = {"gate":"GAP-THEORY-PACKAGE-MAPPING-001","status":"DECLARED_METADATA_CLASSIFICATION_REVIEW_REQUIRED","mode":"metadata-only","home":"morten:theory-cosmos / theory.cosmos.efc-asi / H10","source_repo":"https://github.com/supertedai/EFC","programme_website":"https://energyflow-cosmology.com/","authorial_website":"https://www.magnusson.as/","figshare_author_profile":"https://figshare.com/authors/Morten_Magnusson/20477774","author_identity":"https://orcid.org/0009-0002-4860-5095","counts":counts,"lane_counts":lane_counts,"claim_counts":claim_counts,"rows":rows,"next_action":"Human review of lane_basis and claim_basis; verify DOI/ledger/public provenance before graph projection or steward activation.","mutation":{"graph_write":False,"public_publish":False,"agent_activation":False}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output":str(OUT),"records":len(rows),"lane_counts":lane_counts,"claim_counts":claim_counts},ensure_ascii=False))

if __name__ == "__main__": main()
