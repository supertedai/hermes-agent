#!/usr/bin/env python3
"""BL-4052 mutasjonsbatteri — KJOERER I EN ISOLERT KOPI, ALDRI I DET DELTE TREET.

Forrige versjon muterte filene paa plass i ~/agent-layer/hermes-agent. Det treet
deles av et titalls parallelle oekter og har ~74 endrede filer. Doer kjoereren
midt i en mutant, staar det igjen `if False:` inne i RuntimeSmokeGate.evaluate --
og en parallell `git add -A` (nettopp ae832c8a4-sveipet steg 13 finnes for aa
fange) ville landet en stilltiende avskrudd sikkerhetsvakt.

Et testverktoey med en levende sti til en avskrudd vakt er BL-4052s egen
defektklasse, realisert i verktoeyet som skulle bevise BL-4052. Derfor: kopi
foerst, og en hard paastand om at mutasjonsmaalet ikke ligger i det delte treet.
"""
import shutil
import subprocess
import sys
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent
ISO = Path("/tmp/bl4052-mutation-iso")
VENV = LIVE / ".venv" / "bin" / "python"
FILES = ("agent/code_workflow.py", "agent/faber_postcommit_adapters.py",
         "tests/test_code_workflow.py", "tests/test_faber_postcommit_adapters.py")
TESTS = ["tests/test_code_workflow.py", "tests/test_faber_postcommit_adapters.py"]

CW = "agent/code_workflow.py"
AD = "agent/faber_postcommit_adapters.py"

M = [
    # ---------------- steg 12: RuntimeSmokeGate ----------------
    (CW, "unanswered probe accepted", [("        if not probe.answered:", "        if False:")]),
    (CW, "staleness check disabled",
     [("        if started is not None and mtime is not None and started < mtime:", "        if False:")]),
    (CW, "naive timestamp accepted", [("    if parsed.tzinfo is None:", "    if False:")]),
    (CW, "allowlist widened to admit docker cp",
     [('    ALLOWED_PROBE_METHODS: frozenset[str] = frozenset({"docker exec"})',
       '    ALLOWED_PROBE_METHODS: frozenset[str] = frozenset({"docker exec", "docker cp"})')]),
    (CW, "probe-method check removed",
     [('        elif " ".join(method.lower().split()) not in self.ALLOWED_PROBE_METHODS:', "        elif False:")]),
    (CW, "missing probe method accepted", [("        if not method:", "        if False:")]),
    (CW, "stopped/unknown container accepted", [("        if probe.running is None:", "        if False:")]),
    (CW, "unresolved loaded_path accepted",
     [('        if not (probe.loaded_path or "").strip():', "        if False:")]),
    (CW, "unmeasured digests accepted", [("        if unmeasured:", "        if False:")]),
    (CW, "digest mismatch accepted", [("        elif observed != expected:", "        elif False:")]),
    (CW, "unusable start time accepted", [("        if started is None:", "        if False:")]),
    (CW, "unusable source mtime accepted", [("        if mtime is None:", "        if False:")]),
    # ---------------- mount-analyse ----------------
    (CW, "file invisible in container accepted", [("        if not candidates:", "        if False:")]),
    (CW, "copy outside sys.path[0] accepted", [("        if not under:", "        if False:")]),
    (CW, "ambiguous mount guessed", [("        if len(under) > 1:", "        if False:")]),
    (CW, "unmeasured working dir accepted", [("        if not root:", "        if False:")]),
    (CW, "D4: root working dir collapses to unmeasured",
     [('        return "/" if raw.strip() == "/" else raw.rstrip("/")', '        return raw.rstrip("/")')]),
    (CW, "R14: mount prefix loosened to substring",
     [("        under = [p for p in candidates if p == root or p.startswith(prefix)]",
       "        under = [p for p in candidates if root in p]")]),
    # ---------------- ADR-043 ----------------
    (CW, "unprobed local fleet treated as empty", [("        if not probed:", "        if False:")]),
    (CW, "non-empty local fleet accepted", [("        if names:", "        if False:")]),
    # ---------------- steg 13 ----------------
    (CW, "R10: readback without a sha accepted", [("        if not sha:", "        if False:")]),
    (CW, "unreadable commit accepted", [("        if not readback.resolved:", "        if False:")]),
    (CW, "unreachable/unmeasured reachability accepted",
     [("        if readback.reachable_from_head is None:", "        if False:")]),
    (CW, "unstated expected file set accepted", [("        if not expected:", "        if False:")]),
    (CW, "unknown file set accepted", [("        if readback.files is None:", "        if False:")]),
    (CW, "empty commit accepted", [("        elif not readback.files:", "        elif False:")]),
    (CW, "foreign files accepted", [("            if foreign:", "            if False:")]),
    (CW, "missing expected files accepted", [("            if missing:", "            if False:")]),
    (CW, "commit without its BL ref accepted",
     [("        if ref and ref.lower() not in str(readback.subject).lower():", "        if False:")]),
    (CW, "R13: unparseable timestamp accepted",
     [('    except ValueError:\n        return None, f"unparseable timestamp: {value!r}"',
       '    except ValueError:\n        return datetime(2000, 1, 1, tzinfo=timezone.utc), ""')]),
    # ---------------- PostcommitLoop ----------------
    (CW, "proving steps replayable again",
     [('        never_replay = {"tests", "runtime_smoke", "readback", "rollback"}',
       '        never_replay = {"tests", "runtime_smoke"}')]),
    (CW, "StepBlocked reason discarded",
     [("class StepBlocked(Exception):", "class _NeverRaised(Exception):\n    pass\n\n\nclass StepBlocked(Exception):"),
      ("                    except StepBlocked as blocked:", "                    except _NeverRaised as blocked:")]),
    # ---------------- adaptere ----------------
    (AD, "import smoke: empty change set 'not applicable'",
     [('        raise StepBlocked("runtime_smoke",\n                          f"commit {sha[:12]} touches no files',
       '        return ("not applicable"  # noqa\n                f"commit {sha[:12]} touches no files')]),
    (AD, "import smoke: unreadable/merge commit accepted",
     [("    if touched is None:", "    if False and touched is None:")]),
    (AD, "import smoke: tests/ exclusion dropped",
     [('    if not path.endswith(".py") or path.startswith("tests/"):', '    if not path.endswith(".py"):')]),
    (AD, "import smoke: deleted modules imported again",
     [("    present = _commit_files(sha, repo=repo, only_present=True) or ()",
       "    present = _commit_files(sha, repo=repo) or ()")]),
    (AD, "D2: non-identifier paths become module names",
     [("    if any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):\n        return None",
       "    if False:\n        return None")]),
    (AD, "D3: merge reason collapsed to 'or unreadable'",
     [('               if is_merge_commit(sha, repo=repo) else "the commit is unreadable")',
       '               if False else "the commit is unreadable")')]),
    (AD, "step 13 gate verdict ignored",
     [('    if verdict.status is not PreflightStatus.PASS:\n        raise StepBlocked("readback", "; ".join(verdict.reasons))',
       '    if False:\n        raise StepBlocked("readback", "; ".join(verdict.reasons))')]),
    (AD, "step 12 gate verdict ignored",
     [("    verdict = RuntimeSmokeGate().evaluate(probe)\n    if verdict.status is not PreflightStatus.PASS:",
       "    verdict = RuntimeSmokeGate().evaluate(probe)\n    if False:")]),
    (AD, "missing docker binary treated as failed probe",
     [('    if not had_binary:\n        return True, (), "docker is not installed here',
       '    if False:\n        return True, (), "docker is not installed here')]),
    (AD, "probe reads the host instead of the process",
     [('        source_mtime=source_mtime,\n        probe_method="docker exec",',
       '        source_mtime=source_mtime,\n        probe_method="docker cp",')]),
    (AD, "B2 defeated: expected digest taken from the container's own report",
     [('        expected_digest=(expected_digest or "").strip() or None,', "        expected_digest=observed_digest,")]),
    (AD, "R1: target + no-target declaration accepted together",
     [("    if container and declared:", "    if False:")]),
    (AD, "R2: unreadable expected digest accepted", [("    if not expected:", "    if False:")]),
    (AD, "B1: process check skippable by default again",
     [("    if not container and not declared:", "    if False:")]),
    (AD, "runtime target accepted without the committed path",
     [("    if not repo_relpath.strip():", "    if False:")]),
    (AD, "D5: blank container clears the no-target gate",
     [("    container = container.strip()          # D5: samme normalisering som declared",
       "    container = container  # noqa: PLW0127")]),
    (AD, "symlink reported as a content mismatch",
     [('    if mode in {"120000", "160000"}:', "    if False:")]),
    (AD, "R3: non-blob entries hashed",
     [('    if commit_entry_mode(sha, relpath, repo=repo) not in {"100644", "100755"}:\n        return ""',
       '    if False:\n        return ""')]),
    (AD, "R3b: cat-file failure hashed as empty content",
     [("        if proc.returncode == 0:", "        if True:")]),
    (AD, "N1: commit_entry_mode reads a pathspec match, not the exact path",
     [('    if name != wanted:\n        return ""', '    if False:\n        return ""')]),
    (AD, "N2: commit_entry_mode accepts a multi-entry pathspec",
     [('    if len(records) != 1 or "\\t" not in records[0]:', '    if len(records) < 1 or "\\t" not in records[0]:')]),
    (AD, "merge commit reported as an empty file set",
     [("    if len(parents.split()) > 2:      # sha + >1 forelder\n        return None",
       "    if False:\n        return None")]),
    (AD, "octal-quoted non-ASCII paths reintroduced",
     [('    args = ["diff-tree", "-r", "--no-commit-id", "--name-only", "--root", "-z"]',
       '    args = ["diff-tree", "-r", "--no-commit-id", "--name-only", "--root"]'),
      ('    return tuple(f for f in proc.stdout.split("\\0") if f.strip())',
       "    return tuple(f for f in proc.stdout.splitlines() if f.strip())")]),
    (AD, "ADR-043 asks the remote runtime host",
     [("                                    docker_cmd=docker_cmd or _local_docker_cmd())",
       "                                    docker_cmd=docker_cmd or _default_docker_cmd())")]),
    (AD, "stdout/stderr conflated again",
     [('    if proc.returncode != 0:\n        return proc.returncode, (proc.stderr or proc.stdout).strip(), True\n    return 0, (proc.stdout or "").strip(), True',
       "    return proc.returncode, (proc.stdout or proc.stderr).strip(), True")]),
    (AD, "D1: skipped ADR-043 check not recorded (declared path)",
     [('        fleet_note = "; ADR-043 local-fleet check skipped by caller"', '        fleet_note = ""')]),
    (AD, "N6: skipped ADR-043 check not recorded on the MEASURED path",
     [('            f"(sha256 {expected[:12]}) — written before that start{fleet_note}")',
       '            f"(sha256 {expected[:12]}) — written before that start")')]),
    (AD, "Q2 flag suppressed", [("        if landed_modules(sha, repo=repo)[0]:", "        if False:")]),
    (AD, "Q2 flag reads prose instead of the module count",
     [("        if landed_modules(sha, repo=repo)[0]:", '        if "module(s) imported" in imported:')]),
]


def build_iso() -> None:
    if ISO.exists():
        shutil.rmtree(ISO)
    ISO.mkdir(parents=True)
    tar = subprocess.run(f"git archive HEAD | tar -x -C {ISO}", shell=True, cwd=str(LIVE),
                         capture_output=True, text=True)
    if tar.returncode != 0:
        raise SystemExit(f"git archive failed: {tar.stderr}")
    for rel in FILES:                       # overlay the uncommitted work under review
        shutil.copy2(LIVE / rel, ISO / rel)


def run_tests() -> bool:
    proc = subprocess.run([str(VENV), "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
                          cwd=str(ISO), capture_output=True, text=True, timeout=900)
    return proc.returncode == 0


def main() -> int:
    build_iso()
    # Hard-paastand: ingen mutasjon skal noensinne treffe det delte treet.
    for rel in FILES:
        target = (ISO / rel).resolve()
        assert "hermes-agent" not in str(target), f"REFUSING to mutate the shared tree: {target}"
    if not run_tests():
        print("BASELINE IS RED in the isolated copy — aborting")
        return 2
    print(f"isolated copy {ISO}; baseline green; {len(M)} mutations\n")

    originals = {rel: (ISO / rel).read_text(encoding="utf-8") for rel in {m[0] for m in M}}
    survivors, applied = [], 0
    for rel, label, edits in M:
        text = originals[rel]
        ok = True
        for old, new in edits:
            if text.count(old) != 1:
                print(f"  !! ANCHOR {text.count(old)}x  {label}")
                survivors.append(f"[anchor] {label}")
                ok = False
                break
            text = text.replace(old, new, 1)
        if not ok:
            continue
        (ISO / rel).write_text(text, encoding="utf-8")
        applied += 1
        killed = not run_tests()
        print(f"  {'KILLED ' if killed else 'SURVIVED'}  {label}")
        if not killed:
            survivors.append(label)
        (ISO / rel).write_text(originals[rel], encoding="utf-8")

    # Kjente EKVIVALENTE mutanter: koden er riktig, men mutasjonen endrer ingen
    # observerbar oppfoersel, saa ingen aerlig test kan drepe den. De foeres opp
    # her framfor aa bli "fikset" med en test som later som.
    EQUIVALENT = {"N2: commit_entry_mode accepts a multi-entry pathspec"}
    real = [s for s in survivors if s not in EQUIVALENT]
    equiv = [s for s in survivors if s in EQUIVALENT]
    print(f"\napplied {applied}, survivors {len(survivors)} "
          f"({len(real)} real, {len(equiv)} known-equivalent)")
    for s in equiv:
        print("  EQUIVALENT (expected):", s)
    for s in real:
        print("  SURVIVOR:", s)
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
