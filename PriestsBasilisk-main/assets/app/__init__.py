"""basilisk_assets — the app's runtime art, as an importable package.

This directory has two jobs and exactly one copy of the files.

  * In the REPO and under install.sh it is plain old ``assets/app/``.  The
    installer copies the named art out of here into the flat installed layout
    (``~/.local/share/basilisk/``), exactly as before.  Nothing about that path
    changed.
  * In the WHEEL it is imported as the package ``basilisk_assets``.
    pyproject.toml maps the name onto this directory with
    ``[tool.setuptools.package-dir]``, so the art ships inside the package
    instead of being scattered into the root of site-packages — and there is
    still only one copy of a 7 MB asset tree in the repo.

``basilisk._asset_paths()`` looks here last, after the installed and repo
locations, so a dev checkout and an install.sh install both behave exactly as
they did before this file existed.

Nothing imports symbols from here; the module exists so the directory is a
package.  ``path()`` is a convenience for callers that would rather not think
about ``__file__``.
"""

from __future__ import annotations

import os

__all__ = ["ASSET_DIR", "path"]

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def path(filename: str) -> str:
    """Absolute path to a bundled asset.  Does not check that it exists."""
    return os.path.join(ASSET_DIR, filename)
