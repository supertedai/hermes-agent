"""The launcher publisher may not bind a running installation to another home.

Measured on the Hetzner host 2026-09-30 (cards ``t_04285d23`` / ``t_242ca5f0``):
a pytest run resolved its store interpreter from a SANDBOX ``HERMES_HOME`` and
published it into the RUNNING installation's own launcher
(``<live tree>/.hermes/bin/hermes``). Every ``hermes`` call on the host then died
with ``exec: …/test_flytt_frem_og_tilbake0/hermes/tools/…: not found``, and the
kanban dispatcher stood still for 2h44m — no watchdog could see it, because the
watchdogs run through that very file.

``hermes_state_guard`` / ``hermes_state._ensure_test_isolation`` close this class
for ``state.db``. These tests pin the publisher's two escapes:

* a test process may not republish the live installation at all, and
* a MANAGED installation (``<home>/hermes-agent``) may only be published with a
  store from its own home — the sandbox interpreter the incident wrote.

Every tree here is a temporary stand-in for the live installation: the real tree
is never named, probed or touched by these tests.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import hermes_state_guard
from hermes_cli import _launchers

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Markers hermes_constants uses to recognize a Hermes home. A directory that
#: carries one (or profiles/ or a store of its own) OWNS the installations under
#: it; a bare checkout does not.
HOME_MARKER = "config.yaml"


def platform_home_dir(user_home: Path) -> Path:
    """Where the platform keeps its home for *user_home* (LOCALAPPDATA on Windows)."""
    return user_home / "hermes" if os.name == "nt" else user_home / ".hermes"


def store_for(home: Path, entry: str = "python-3.14.7+fixture") -> Path:
    """A PM store under *home*: ``facts.json`` plus the interpreter it records."""
    store = home / "tools"
    interpreter = store / entry / ("python.exe" if os.name == "nt" else "bin/python3")
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    interpreter.chmod(0o755)
    (store / "facts.json").write_text(
        json.dumps({"schema": 1, "packages": {"python": {"entry": entry}}}), encoding="utf-8")
    return interpreter


def stand_in_installation(tmp_path, monkeypatch, *, home: Path | None = None,
                          tree: Path | None = None) -> tuple[Path, Path]:
    """A managed installation shaped exactly like the live one.

    ``<home>/hermes-agent`` under a home that carries the home markers. *home*
    defaults to the platform's own home for a stand-in user, so the guard reads
    this tree as the LIVE installation while the real ``~/.hermes`` is never in
    play: HOME (which ``expanduser("~")`` reads) is redirected to the stand-in.
    """
    user_home = tmp_path / "user"
    user_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(user_home))
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(user_home))
    home = home if home is not None else platform_home_dir(user_home)
    tree = tree if tree is not None else home / "hermes-agent"
    home.mkdir(parents=True, exist_ok=True)
    (home / HOME_MARKER).write_text("cli: {}\n", encoding="utf-8")
    local = tree / ".hermes" / "bin"
    local.mkdir(parents=True, exist_ok=True)
    (local / "hermes").write_text("#!/bin/sh\n# published by a previous run\nexit 1\n", encoding="utf-8")
    (local / "hermes").chmod(0o755)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_RUNTIME_DIR", raising=False)
    monkeypatch.delenv(_launchers._LAUNCHER_GUARD_BYPASS_ENV, raising=False)
    return tree, home


def published_bytes(tree: Path) -> bytes:
    return (tree / ".hermes" / "bin" / "hermes").read_bytes()


def assert_nothing_published(tree: Path, before: bytes) -> None:
    local = tree / ".hermes" / "bin"
    assert published_bytes(tree) == before, "the publisher wrote a launcher despite refusing"
    assert not list(local.glob("*.stage.*")), "a staging file was left behind"
    assert not (local / "hermes-acp").exists(), "the second launcher was published too"


@pytest.mark.platforms("posix", "windows")
def test_a_test_process_never_republishes_the_live_installation(tmp_path, monkeypatch):
    """The live tree's own store is no excuse: a test must not write it at all."""
    tree, home = stand_in_installation(tmp_path, monkeypatch)
    store_for(home)  # consistent: only the test-context clause can refuse this
    before = published_bytes(tree)

    with pytest.raises(_launchers.LauncherPublicationRefused) as refused:
        _launchers.ensure_install_launchers(tree, tree / ".hermes" / "bin")

    message = str(refused.value)
    assert str(tree) in message, "the refusal must name the installation it refused"
    assert _launchers._LAUNCHER_GUARD_BYPASS_ENV in message, "the refusal must name its escape hatch"
    assert_nothing_published(tree, before)


@pytest.mark.platforms("posix", "windows")
def test_the_guard_is_escapable_by_a_deliberate_caller(tmp_path, monkeypatch):
    """A run that genuinely needs the live tree opts out explicitly, not silently."""
    tree, home = stand_in_installation(tmp_path, monkeypatch)
    interpreter = store_for(home)
    before = published_bytes(tree)
    monkeypatch.setenv(_launchers._LAUNCHER_GUARD_BYPASS_ENV, "1")

    published = _launchers.ensure_install_launchers(tree, tree / ".hermes" / "bin")

    assert published, "the sanctioned bypass must still publish"
    assert published_bytes(tree) != before
    assert str(interpreter) in published_bytes(tree).decode("utf-8")


@pytest.mark.platforms("posix")
def test_a_store_from_a_sandbox_home_is_refused(tmp_path, monkeypatch):
    """The incident's exact shape, on an installation no test-context clause covers.

    The tree lives under its own (custom) home and the process's ``~`` is
    elsewhere, so only the store/home mismatch can refuse this — which is what
    wrote the sandbox interpreter into a real launcher.
    """
    custom = tmp_path / "shared-hermes"
    tree, home = stand_in_installation(tmp_path, monkeypatch, home=custom)
    sandbox = tmp_path / "pytest-base" / "test_flytt_frem_og_tilbake0" / "hermes"
    sandbox_interpreter = store_for(sandbox)
    monkeypatch.setenv("HERMES_HOME", str(sandbox))
    before = published_bytes(tree)

    with pytest.raises(_launchers.LauncherPublicationRefused) as refused:
        _launchers.ensure_install_launchers(tree, tree / ".hermes" / "bin")

    message = str(refused.value)
    assert str(sandbox_interpreter) not in published_bytes(tree).decode("utf-8")
    assert str(home) in message and str(sandbox) in message, message
    assert_nothing_published(tree, before)

    # The same installation published from its OWN home is the normal path.
    store_for(home)
    monkeypatch.setenv("HERMES_HOME", str(home))
    assert _launchers.ensure_install_launchers(tree, tree / ".hermes" / "bin")


@pytest.mark.platforms("posix", "windows")
def test_a_checkout_outside_any_home_keeps_publishing(tmp_path, monkeypatch):
    """A developer checkout has no owning home: the store comes from the process.

    Without this, an ordinary ``HERMES_HOME``/``HERMES_RUNTIME_DIR`` pinned
    development tree would be refused and publication would be unusable.
    """
    user_home = tmp_path / "user"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(user_home))
    checkout = tmp_path / "checkout" / "hermes-agent"
    (checkout / ".hermes" / "bin").mkdir(parents=True)
    dev_home = tmp_path / "dev-home"
    interpreter = store_for(dev_home)
    monkeypatch.setenv("HERMES_HOME", str(dev_home))
    monkeypatch.delenv("HERMES_RUNTIME_DIR", raising=False)
    monkeypatch.delenv(_launchers._LAUNCHER_GUARD_BYPASS_ENV, raising=False)

    published = _launchers.ensure_install_launchers(checkout, checkout / ".hermes" / "bin")

    assert published
    assert str(interpreter) in (checkout / ".hermes" / "bin" / "hermes").read_text(encoding="utf-8")


@pytest.mark.platforms("posix", "windows")
def test_the_documented_recovery_command_still_publishes(tmp_path, monkeypatch):
    """The one command a human runs on the host must keep working.

    ``docs/starteren-gjenoppretting.md`` (Hetzner) names exactly this call. It is
    a host shell, not a pytest run: the test-context signals are what the suite
    adds, so clear them here to model the human's process.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("HERMES_TEST_ISOLATION", raising=False)
    monkeypatch.setattr(hermes_state_guard, "_PYTEST_ANCESTOR", False)
    tree, home = stand_in_installation(tmp_path, monkeypatch)
    interpreter = store_for(home)
    before = published_bytes(tree)

    published = _launchers.ensure_install_launchers(tree, tmp_path / "user" / ".local" / "bin")

    assert published, "the recovery command must still publish"
    assert published_bytes(tree) != before
    assert str(interpreter) in published_bytes(tree).decode("utf-8")


#: Child probe: the guard is asked directly, so a regression here cannot write.
_CHILD_PROBE = """
import json, sys
sys.path.insert(0, {repo!r})
from pathlib import Path
from hermes_cli import _launchers
try:
    _launchers._refuse_unsafe_publication(Path({tree!r}))
except _launchers.LauncherPublicationRefused as exc:
    print(json.dumps({{"verdict": "REFUSED", "error": type(exc).__name__}}))
else:
    print(json.dumps({{"verdict": "ALLOWED"}}))
"""


def run_child_probe(tree: Path, env: dict) -> dict:
    proc = subprocess.run([sys.executable, "-c", _CHILD_PROBE.format(repo=str(REPO_ROOT), tree=str(tree))],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def scrubbed_child_env(**overrides) -> dict:
    """A child whose environment was rebuilt from scratch (#82770's shape)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PYTEST_") and k not in ("HERMES_HOME", "HERMES_TEST_ISOLATION")}
    env.update(overrides)
    return env


@pytest.mark.platforms("posix", "windows")
def test_a_child_with_a_rebuilt_environment_is_still_refused(tmp_path, monkeypatch):
    """Ancestry survives the env rebuild that takes PYTEST_* and the marker away."""
    tree, home = stand_in_installation(tmp_path, monkeypatch)
    store_for(home)
    env = scrubbed_child_env(HOME=os.environ["HOME"], HERMES_HOME=str(home))
    if os.name == "nt":
        env["LOCALAPPDATA"] = os.environ["LOCALAPPDATA"]

    probe = run_child_probe(tree, env)
    assert probe["verdict"] == "REFUSED", (
        "a child that lost PYTEST_* and the isolation marker republished the live "
        "installation — the publisher's #82770-shaped escape is open"
    )
    assert probe["error"] == "LauncherPublicationRefused", (
        "the refusal must be the named error, not a bare RuntimeError"
    )


@pytest.mark.platforms("posix", "windows")
def test_the_child_escape_hatch_crosses_the_process_boundary(tmp_path, monkeypatch):
    tree, home = stand_in_installation(tmp_path, monkeypatch)
    store_for(home)
    env = scrubbed_child_env(HOME=os.environ["HOME"], HERMES_HOME=str(home),
                             **{_launchers._LAUNCHER_GUARD_BYPASS_ENV: "1"})

    assert run_child_probe(tree, env)["verdict"] == "ALLOWED"
