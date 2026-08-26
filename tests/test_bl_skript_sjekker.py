"""Kjører BL-skript-sjekkene i subprosess, og teller dem for pytest.

De to skriptene er skrevet som selvstendige sjekker: hele kroppen kjører
ved import, og de setter prosess-global tilstand — ``skript_bl3432``
setter ``SYMBIOSE_USERS_HOME`` og rører ``sys.path`` uten å rydde opp.
Importert inn i en delt pytest-sesjon lekker det: målt her veltet
``skript_bl3432`` testen
``test_home_channels_lists_only_platforms_with_home`` i
``tests/plugins/test_kanban_dashboard_plugin.py``, som passerer alene.

CI kjører hver fil isolert, så lekkasjen rammer ikke CI — men en
utvikler som kjører pytest over flere filer lokalt får en feil som ikke
er der. Derfor: skriptene heter ikke lenger ``test_*`` (og samles
dermed ikke), og kjøres i stedet herfra i hver sin subprosess. Ekte
dekning, ingen lekkasje.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent

SKRIPT = (
    "skript_bl3404_selvregistrering.py",
    "skript_bl3432_kapabilitet.py",
)


@pytest.mark.parametrize("navn", SKRIPT)
def test_bl_skript_passerer(navn: str) -> None:
    sti = _TESTS_DIR / navn
    assert sti.exists(), f"skript mangler: {sti}"
    kjort = subprocess.run(
        [sys.executable, str(sti)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )
    assert kjort.returncode == 0, kjort.stdout + kjort.stderr
