#!/usr/bin/env python3
"""Build a metadata-only TheoryHomeRecord inventory for the local EFC checkout."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2] / "symbiose-workspace" / "EFC"
PACKAGES = REPO / "docs" / "papers" / "efc"
PUBLIC = REPO / "docs" / "public"
OUT = Path(__file__).resolve().parents[1] / "docs" / "mwp-h10-theory-home-inventory-v1.json"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def lane_for(package: str, text: str) -> tuple[str, str]:
    hay = f"{package} {text}".lower()
    if "rcmp" in hay or "regime-consistent" in hay:
        return "RCMP", "methodology"
    if any(x in hay for x in ("entropy-bounded", "ebe", "l0–l3", "l0-l3")):
        return "EBE/S0-S1/L0-L3", "epistemology/regime"
    if any(x in hay for x in ("consciousness", "cognitive", "autopoiesis", "homo fluxus", "symbiosis")):
        return "consciousness/meta/cognition", "meta/cognition"
    if any(x in hay for x in ("prediction", "validation", "kill-test", "empirical", "preregister")):
        return "EFC validation/prediction", "empirical/prediction"
    return "EFC core/cosmos", "theory"


def public_refs(package: str) -> list[str]:
    refs: list[str] = []
    for path in sorted(PUBLIC.glob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".md", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if package in text:
            refs.append(str(path.relative_to(REPO)))
    return refs[:20]


def main() -> None:
    rows: list[dict[str, Any]] = []
    for readme in sorted(PACKAGES.rglob("README.md")):
        package_dir = readme.parent
        rel_dir = package_dir.relative_to(PACKAGES)
        if not rel_dir.parts or rel_dir.parts == ("_archived",):
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")[:30000]
        except OSError:
            text = ""
        package = str(rel_dir)
        index = read_json(package_dir / "index.json")
        manifest = package_dir / "MANIFEST.md"
        doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
        lane, kind = lane_for(package, text)
        rows.append({
            "package_id": package,
            "readme": str(readme.relative_to(REPO)),
            "index_json": str((package_dir / "index.json").relative_to(REPO)) if index else None,
            "manifest": str(manifest.relative_to(REPO)) if manifest.exists() else None,
            "title": (index or {}).get("title") if index else None,
            "doi": (index or {}).get("doi") if index else (doi_match.group(0) if doi_match else None),
            "lane_discovery": lane,
            "kind_discovery": kind,
            "source_layer": "paper_package",
            "has_schema": any(package_dir.glob("**/*schema*.json")),
            "has_data": (package_dir / "data").is_dir(),
            "has_source": (package_dir / "src").is_dir(),
            "has_pdf": any(package_dir.glob("*.pdf")),
            "public_refs": public_refs(package_dir.name),
            "claim_status": "UNCLASSIFIED",
            "graph_projection_status": "NOT_PROBED",
            "steward": "efc-asi-steward (PROPOSED_NOT_LIVE_VERIFIED)",
            "readback_status": "DECLARED_HEURISTIC",
        })
    output = {
        "gate": "GAP-THEORY-PACKAGE-MAPPING-001",
        "status": "DECLARED_PACKAGE_INVENTORY_CLAIM_CLASSIFICATION_PENDING",
        "mode": "metadata-only",
        "source_repo": str(REPO),
        "source_remote": "https://github.com/supertedai/EFC",
        "public_surface": str(PUBLIC.relative_to(REPO)),
        "home": "morten:theory-cosmos / theory.cosmos.efc-asi / H10",
        "steward": "efc-asi-steward (PROPOSED_NOT_LIVE_VERIFIED)",
        "counts": {"records": len(rows), "public_files": len(list(PUBLIC.glob("*")))},
        "rows": rows,
        "next_action": "Classify claim/evidence/prediction status from package index/schema/ledger and obtain source commit/DOI readback before graph projection.",
        "mutation": {"graph_write": False, "public_publish": False, "agent_activation": False},
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "records": len(rows), "public_files": output["counts"]["public_files"]}))


if __name__ == "__main__":
    main()
