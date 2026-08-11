#!/usr/bin/env python3
"""Build a candidate-only Neo4j label classification from authority metadata."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

INPUT = Path("docs/mwp-neo4j-full-authority-metadata-audit-v1.json")
OUTPUT = Path("docs/mwp-neo4j-label-candidate-classification-v1.json")
RULES = {
    "deprecated_legacy_quarantine_candidate": r"deprecated|archived|orphan|legacy|quarantine",
    "event_telemetry_observation_candidate": r"event|telemetry|measurement|reading|signal|log|trace|audit",
    "memory_knowledge_content_candidate": r"memory|fact|claim|document|chunk|knowledge|conversation|concept|pattern",
    "agent_workflow_execution_candidate": r"agent|task|workflow|run|session|job|action|goal|project|proposal",
    "schema_governance_candidate": r"schema|constraint|index|ontology|taxonomy|framework|architecture|standard",
    "domain_entity_candidate": r"patient|biology|country|company|asset|person|research|energy|health",
}

def classify(label: str) -> str:
    low = label.lower()
    for category, pattern in RULES.items():
        if re.search(pattern, low):
            return category
    return "unclassified_owner_review_required"

def main() -> int:
    source = json.loads(INPUT.read_text())
    labels = source["labels"]
    constrained = set()
    indexed = set()
    # Full metadata artifact does not preserve per-row constraint/index mappings;
    # keep authority counts and make classification explicitly candidate-only.
    candidates = {label: classify(label) for label in labels}
    category_counts = Counter(candidates.values())
    samples = defaultdict(list)
    for label, category in candidates.items():
        if len(samples[category]) < 50:
            samples[category].append(label)
    out = {
        "artifact_id": "mwp-neo4j-label-candidate-classification-v1",
        "mwp_id": "MWP-UOSH-001",
        "phase": "P7",
        "status": "CANDIDATE_CLASSIFICATION_OWNER_REVIEW_REQUIRED",
        "source": str(INPUT),
        "classification_mode": "heuristic_name_only_candidate_not_authority",
        "label_count": len(labels),
        "category_counts": dict(category_counts),
        "category_samples": {k: sorted(v) for k, v in samples.items()},
        "all_labels": candidates,
        "safety": {
            "writes_allowed": False,
            "no_ontology_promotion": True,
            "no_schema_repair": True,
            "no_deduplication": True,
            "owner_review_required": True,
        },
        "next_action": "join each candidate label with live constraint/index/property/relationship coverage and assign verified owner/domain/lifecycle role",
    }
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(OUTPUT), "label_count": len(labels), "category_counts": dict(category_counts), "writes_allowed": False}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
