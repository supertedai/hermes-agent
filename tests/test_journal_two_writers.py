"""To skrivere mot én journal — vakten der defekten faktisk bor (BL-4029 L6/L7).

Denne testen ligger med vilje ikke inne i `faber_goal_state` eller i
`faber_control_bridge`, men MELLOM dem. Begge modulene er korrekte hver for seg;
defekten oppstår først når to produsenter med ulikt fasevokabular deler journal —
og da ser hver av dem fortsatt riktig ut i sine egne tester.

Det er samme lærdom som L4: invarianten må voktes DER TO PRODUSENTER MØTES, ikke
inne i én av dem.
"""

from __future__ import annotations

from pathlib import Path

from agent import faber_goal_state as gs


def _observe_tick():
    """Slik `faber_observe` -> `faber_goal_state` skriver."""
    return {"goal_id": "g1", "stopped_by": "preflight", "preflight": "BLOCK",
            "reasons": ["target lease is not clear"], "gate": "reviewer"}


def _bridge_tick():
    """Slik `faber_control_bridge` skriver — samme mål, annet vokabular."""
    return {"goal_id": "g1", "phase": "planned_through_13_awaiting_execution",
            "outcome": "PLANNED", "reasons": [], "gate": "GO_READ_ONLY"}


def test_one_writer_accumulates_a_streak(tmp_path: Path):
    """Referansen: én produsent, uendret verden, streken vokser."""
    j = tmp_path / "j.json"
    for _ in range(5):
        gs.record_all([_observe_tick()], path=j)
    row = gs.summarise(gs.load(j))["rows"][0]
    assert row["unchanged_ticks"] == 4
    assert row["history_total"] == 1, "én uendret sannhet skal gi ÉN historikk-oppføring"


def test_two_writers_on_one_journal_destroy_the_streak(tmp_path: Path):
    """DEFEKTEN, målt — dokumentert her så den ikke gjenoppstår.

    Verden endrer seg ikke én eneste gang. Kun fasevokabularet veksler. Men
    `record()` regner `same` av `(digest, phase, outcome)`, så hver tick leses som
    en endring:

      - `unchanged_ticks` blir stående på 0 for alltid
      - `history` vokser med én oppføring per tick — altså 338-linjer-én-fakta-
        defekten fra `activation-todo.log`, gjeninnført i journalen som ble bygget
        for å fjerne den
      - `last_change_at` flytter seg hver tick, så BL-4006s hovedsetning er
        permanent usann
    """
    j = tmp_path / "shared.json"
    for _ in range(6):
        gs.record_all([_observe_tick()], path=j)
        gs.record_all([_bridge_tick()], path=j)

    row = gs.summarise(gs.load(j))["rows"][0]
    assert row["unchanged_ticks"] == 0, "delt journal: streken kan aldri akkumulere"
    assert row["history_total"] >= 12, (
        "delt journal: én historikk-oppføring per tick — dette ER defekten"
    )


def test_separate_journals_preserve_both_streaks(tmp_path: Path):
    """FIKSEN: ulike spørsmål, ulike journaler. Begge streker overlever.

    De to måler ikke det samme — preflight-status mot 13-stegs planleggingsdybde —
    og `unchanged_ticks` er bare meningsfull når påfølgende observasjoner er
    sammenlignbare.
    """
    ja, jb = tmp_path / "observe.json", tmp_path / "bridge.json"
    for _ in range(5):
        gs.record_all([_observe_tick()], path=ja)
        gs.record_all([_bridge_tick()], path=jb)

    a = gs.summarise(gs.load(ja))["rows"][0]
    b = gs.summarise(gs.load(jb))["rows"][0]
    assert a["unchanged_ticks"] == 4 and a["history_total"] == 1
    assert b["unchanged_ticks"] == 4 and b["history_total"] == 1


def test_shared_journal_also_clobbers_the_phantom_tick_guard(tmp_path: Path):
    """Kollisjonen under kollisjonen.

    `source_observed_at` er BL-4006s fantom-tick-vakt, og den er ÉN verdi per
    journal. To skrivere med hver sin snapshot-id overskriver hverandres markør,
    så vakten er satt ut av spill for begge — uten at noen av dem merker det.
    """
    j = tmp_path / "shared.json"
    gs.record_all([_observe_tick()], path=j, observed_at="OBSERVE-SNAP-1")
    gs.record_all([_bridge_tick()], path=j, observed_at="BRIDGE-SNAP-1")

    # Observes egen snapshot-id er borte -> dens neste tick blir IKKE hoppet over,
    # selv om snapshotet er uendret.
    res = gs.record_all([_observe_tick()], path=j, observed_at="OBSERVE-SNAP-1")
    assert res["status"] == "EXECUTED", (
        "vakten skulle sagt SKIPPED — den andre skriveren har overskrevet markøren"
    )
