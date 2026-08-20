"""
setup.py — wheel/sdist build guard.

pip/PyPI and Homebrew are no longer supported distribution methods for
Hermes Agent (see website/docs/getting-started/platform-support.md). The
wheel would ship without bundled assets (locales, skills, optional-mcps,
web_dist, tui_dist, plugin manifests) since those are resolved at runtime
via env-var overrides set by the nix wrapper or the source-checkout layout.

This file overrides the ``bdist_wheel`` and ``sdist`` setuptools commands
to raise an error when run outside a Nix build. The PEP 517
``build_wheel`` / ``build_sdist`` hooks in
``setuptools.build_meta`` call these commands internally, so the guard
fires for ``uv build``, ``pip wheel``, ``python -m build``, and direct
``setup.py`` invocations alike.

The one legitimate consumer of ``build_wheel`` is uv2nix, which calls
``setuptools.build_meta.build_wheel`` (→ ``bdist_wheel``) inside a Nix
build sandbox. ``nix/python.nix`` sets ``HERMES_NIX_BUILD=1`` on the
Hermes package derivation, so only that build may create an artifact.

Editable installs (``uv sync``, ``pip install -e .``, ``nix develop``)
use ``build_editable``, which does NOT call ``bdist_wheel`` — it calls
``build_ext`` in editable mode. So the guard does not affect development.
"""

import os
import tempfile

from setuptools import setup
from setuptools.command.build import build
from setuptools.command.egg_info import egg_info
from setuptools.command.sdist import sdist

_IN_NIX_BUILD = os.environ.get("HERMES_NIX_BUILD") == "1"

_BLOCK_MESSAGE = (
    "Building wheels or sdists for hermes-agent is not supported.\n"
    "Hermes is distributed via the shell installer, Docker image, or Nix.\n"
    "See: https://hermes-agent.nousresearch.com/docs/getting-started/installation\n"
    "\n"
    "If you are developing, use an editable install instead:\n"
    "  uv sync          # or: uv pip install -e .\n"
    "\n"
    "If you are building with Nix (uv2nix), this error should not fire —\n"
    "the Hermes Nix derivation sets HERMES_NIX_BUILD=1. If it does, file a bug."
)


class _GuardedSdist(sdist):
    def run(self, *args, **kwargs):
        if not _IN_NIX_BUILD:
            raise RuntimeError(_BLOCK_MESSAGE)
        return super().run(*args, **kwargs)


def _source_tree_is_writable() -> bool:
    return os.access(os.path.dirname(os.path.abspath(__file__)) or ".", os.W_OK)


class _TemporaryOutputsBuild(build):
    """Redirect build output when the checkout is read-only.

    The Docker WebUI install surface runs setup from a read-only
    /opt/hermes tree; writing ``build/`` metadata there crashes the
    install. Redirect build_base to a temp dir in that case — including
    when a caller passed a source-relative build_base explicitly.
    """

    def finalize_options(self):
        if not _source_tree_is_writable():
            self.build_base = tempfile.mkdtemp(prefix="hermes-agent-build-")
        super().finalize_options()


class _TemporaryOutputsEggInfo(egg_info):
    """Same redirection for egg-info metadata (written even by pip's
    metadata inspection, which otherwise touches the source tree)."""

    def finalize_options(self):
        if not _source_tree_is_writable():
            self.egg_base = tempfile.mkdtemp(prefix="hermes-agent-egg-info-")
        super().finalize_options()


cmdclass = {
    "sdist": _GuardedSdist,
    "build": _TemporaryOutputsBuild,
    "egg_info": _TemporaryOutputsEggInfo,
}

# bdist_wheel is only available when the `wheel` package is installed.
# setuptools.build_meta.build_wheel() calls it internally, so the guard
# fires for all PEP 517 wheel build paths. Define the subclass only when
# the import succeeds — otherwise a None base class raises TypeError at
# class-definition time, before the cmdclass guard can run.
try:
    from setuptools.command.bdist_wheel import bdist_wheel

    class _GuardedBdistWheel(bdist_wheel):
        def run(self, *args, **kwargs):
            if not _IN_NIX_BUILD:
                raise RuntimeError(_BLOCK_MESSAGE)
            return super().run(*args, **kwargs)

    cmdclass["bdist_wheel"] = _GuardedBdistWheel
except ImportError:
    pass

setup(cmdclass=cmdclass)
