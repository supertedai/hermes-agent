"""Live Faber code-agent adapter for the governed chat bridge.

BL-4057: «Use your own ... skills» var en PÅSTAND, ikke en mekanisme. Setningen
sto her på linje 16 og var hele koblingen mellom 1026 SKILL.md på disk og denne
kjeden — den ba modellen huske at den har skills. Grep på select_skill /
choose_skill / match_skill / relevant_skill ga null treff i hele repoet.

Nå velges skillene FØR kallet, av `agent.skill_selector`, mot en indeks med målt
dekning, og valget skrives til et spor som kan leses etterpå. Systemprompten
bærer navnene på de faktisk valgte skillene i stedet for en oppfordring om å
huske.
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any

from agent.continuous_pipeline import default_live_model_resolver
from agent.faber_coding_ingress import evaluate_coding_turn
from agent.skill_selector import render_for_prompt, select_for_task

_MAX_REVIEW_CHARS = int(os.environ.get("FABER_MAX_REVIEW_CHARS", "12000"))
_SKILL_LIMIT = int(os.environ.get("FABER_SKILL_LIMIT", "3"))
_ACTIVE: set[str] = set()
_LOCK = threading.RLock()
_SYSTEM = """You are Faber, the governed code-agent. Review the supplied code-related turn. Do not edit files, execute commands, commit, land, or ACT. Return JSON only with keys: status, preflight, regression, tests_run, tests_passed, confidence, rollback_available, provenance, reason, gate. Never include raw text, code, secrets, or summary in JSON. Missing evidence means NEEDS_REVIEW."""


def _json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"status": "NEEDS_REVIEW", "gate": "faber_output_parse", "reason": "no JSON readback"}
    try:
        output = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"status": "NEEDS_REVIEW", "gate": "faber_output_parse", "reason": "invalid JSON readback"}
    return output if isinstance(output, dict) else {"status": "NEEDS_REVIEW", "gate": "faber_output_shape", "reason": "readback not object"}


def run_live_faber_review(*, raw_text: str, envelope: Any) -> dict[str, Any]:
    """Run Faber in its own session after re-checking ingress gates."""
    goal_id = str(envelope.goal_id)
    if not raw_text.strip():
        return {"status": "BLOCK", "gate": "empty_turn", "reason": "empty code turn"}
    if len(raw_text) > _MAX_REVIEW_CHARS:
        return {"status": "BLOCK", "gate": "review_size", "reason": "code turn exceeds bounded review size"}
    gate = evaluate_coding_turn(
        raw_text,
        session_key=f"faber-review:{goal_id}",
        session_id=str(envelope.session_id),
        turn_index=0,
        surface="faber.review",
    )
    if not gate.admitted:
        return {"status": "BLOCK", "gate": "ingress_recheck", "reason": "Faber ingress gate did not admit review"}
    with _LOCK:
        if goal_id in _ACTIVE:
            return {"status": "NEEDS_REVIEW", "gate": "duplicate_inflight", "reason": "review already running for goal"}
        _ACTIVE.add(goal_id)
    agent = None
    try:
        # Seleksjonen står INNENFOR try/finally.
        #
        # Reviewer 2026-08-11 (BL-4057 runde 1): den sto over `try`, mellom
        # `_ACTIVE.add(goal_id)` og blokka som eier `finally: _ACTIVE.discard`.
        # En korrupt indeks kastet da ut av den governede stien med goal_id
        # fortsatt i _ACTIVE — så hver senere gjennomgang av samme mål fikk
        # `duplicate_inflight`, permanent, og kalleren logget bare en warning.
        # Nettopp den gaten hvis egen prompt sier «Missing evidence means
        # NEEDS_REVIEW» feilet dermed til INGENTING.
        #
        # Seleksjonen skal uansett ikke kunne felle en kode-gjennomgang: den er
        # en opplysning om hvilke skills som finnes, ikke en betingelse for å
        # kunne vurdere kode.
        try:
            selection = select_for_task(raw_text, stage="faber_live_review",
                                        limit=_SKILL_LIMIT)
            skill_block = render_for_prompt(selection)
        except Exception:  # noqa: BLE001
            selection = None
            skill_block = ("Skill catalog is unavailable for this turn. "
                           "Do not conclude that a relevant skill does not exist.")

        model = default_live_model_resolver("builder")
        from run_agent import AIAgent
        agent = AIAgent(
            model=model,
            session_id=f"faber:{goal_id}",
            platform="faber",
            max_iterations=24,
            skip_context_files=True,
            load_soul_identity=False,
        )
        result = agent.run_conversation(
            "Evaluate this code-relevant turn.\n\n" + raw_text,
            system_message=_SYSTEM + "\n\n" + skill_block,
            persist_user_message=True,
            persist_user_display_kind="faber_internal",
        )
        output = _json(str((result or {}).get("final_response") or ""))
        output["provenance"] = "faber.codex"
        output.setdefault("gate", "faber.governed_review")
        output["content_included"] = False
        # Provenans, ikke innhold: navn og dekning bryter ikke JSON-kontraktens
        # forbud mot raw text/code/secrets/summary, og uten dem er seleksjonen
        # uobserverbar for den som leser resultatet.
        output["skills_selected"] = [s.name for s in selection.selected] if selection else []
        output["skills_considered"] = selection.considered if selection else 0
        output["skill_coverage"] = selection.coverage if selection else "unknown"
        return output
    except Exception as exc:
        return {"status": "BLOCK", "gate": "faber_runtime", "reason": f"Faber runtime unavailable: {type(exc).__name__}"}
    finally:
        try:
            if agent:
                agent.close()
        except Exception:
            pass
        with _LOCK:
            _ACTIVE.discard(goal_id)
