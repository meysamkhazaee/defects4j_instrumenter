# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.5] - 2026-11-24

### Added
- Centralized `VERSION` file as the single source of truth, dynamically loaded by:
  - `pyproject.toml` via `[tool.setuptools.dynamic] version = {file = "VERSION"}`.
  - `defects4j_efl_instrumenter/__init__.py`, `cli.py`, and `runner.py`.
  - `run_defects4j.py` orchestrator script.
  - `java-agent/build.py` generating `Implementation-Version` inside `MANIFEST.MF`.
- Automatic download support for the Defects4J v3.0.1 archive (`defects4j-3.0.1.zip`).
- High-level orchestrator script `run_defects4j.py` for automated Java agent compilation, Defects4J extraction, multi-threaded test execution, and dataset generation.
- Full Persian technical guide: `README_FA.md`.

### Changed
- Standardized CLI version reporting (`--version`) across `defects4j-efl-data` and `run_defects4j.py`.
- Synchronized cache fingerprinting to consume `__version__`.

## [1.3.0] - 2026-11-21

### Added
- Linux / WSL2 automated execution environment via `scripts/run_linux.sh`.
- Multi-process parallel worker execution with dynamic CPU/RAM allocation.
- Execution trace cache framework with SHA-256 fingerprinting (`cache_support.py`).
- Full support for 17 Defects4J benchmark projects (838 bugs) and SCD4FL 6-project profile (395 bugs).

## [1.2.0] - 2026-11-21

### Added
- Bytecode `ClassScanner` tool mapping bytecode instructions to source line predicates.
- Differential git diff analysis for automated fault predicate identification.
- Coincidental Correctness (CC) classification and dual dataset generation (`_dataset.txt` binary vs. `_tagged.txt` 3-state).

## [1.1.0] - 2026-11-21

### Added
- Core CLI `defects4j-efl-data` with subcommands: `inspect`, `prepare`, `list`, and `instrument`.
- Structured console progress bars and configurable logging levels.

## [1.0.0] - 2026-11-21

### Added
- Initial ASM-based Java Agent for runtime bytecode instrumentation.
- Ordered execution trace capture into compact binary format.
- Defects4J test execution harness.
