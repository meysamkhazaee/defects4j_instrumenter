"""Defects4J ordered-trace instrumenter for EFL."""

from pathlib import Path


def _load_version() -> str:
    """Read version dynamically from VERSION file or package metadata."""
    candidates = [
        Path(__file__).resolve().parent.parent / "VERSION",
        Path(__file__).resolve().parent / "VERSION",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    try:
        from importlib.metadata import version
        return version("defects4j-efl-instrumenter")
    except Exception:
        return "1.3.5"


__version__ = _load_version()

