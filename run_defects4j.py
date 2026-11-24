#!/usr/bin/env python3
"""
Defects4J Benchmark Suite: Automated Instrumentation Runner & Dataset Generator.

Capabilities:
  1. Automated Java Agent compilation and deployment (ASM-based bytecode instrumentation).
  2. Multi-threaded / multi-process execution of Defects4J bug versions.
  3. Extraction of trace P-points (execution paths) and mapping to source code line predicates.
  4. Automatic identification of fault predicates via git diff analysis (source_changes.json + source_map.csv).
  5. Classification of every test case into:
     - PASS (T): Test passed, fault predicate was NOT visited.
     - COINCIDENTAL_CORRECT (CC / T): Test passed, BUT fault predicate WAS visited!
     - FAIL (F): Test failed (oracle mismatch / exception).
  6. Generation of standard ML / FL dataset files matching the Siemens format:
     - <version>_dataset.txt: Lines 1..N execution P-traces, Line N+1 verdict vector (T,T,T,F,...).
     - <version>_tagged.txt: Lines 1..N execution P-traces, Line N+1 tagged verdicts (T,CC,F,...).
     - <version>_detailed.json: Full structural metadata and test-by-test breakdown.
     - cmp.v0.v<bug>.<project>.csv: EFL Stage 2 compatible CSV feed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

# Add package root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from defects4j_efl_instrumenter import __version__
from defects4j_efl_instrumenter.agent import ensure_agent
from defects4j_efl_instrumenter.commands import configure_java_home, resolve_defects4j
from defects4j_efl_instrumenter.framework import prepare_defects4j
from defects4j_efl_instrumenter.models import BugRef
from defects4j_efl_instrumenter.progress import ConsoleReporter, LogLevel
from defects4j_efl_instrumenter.runner import (
    PAPER_PROFILE,
    discover_projects,
    instrument_suite,
    resolve_bugs,
    resolve_instrument_jobs,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Defects4J Automated Instrumentation & Dataset Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--defects4j",
        type=Path,
        default=None,
        help="Path to Defects4J archive (.zip) or initialized root directory (or DEFECTS4J_HOME / DEFECTS4J_PATH env)",
    )
    parser.add_argument(
        "--java-home",
        type=Path,
        default=None,
        help="Path to JDK 11 installation (or JAVA_HOME env)",
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=SCRIPT_DIR / "output",
        help="Output working directory for checkouts, instrumentation results, and datasets",
    )
    parser.add_argument(
        "--projects",
        type=str,
        default=None,
        help="Comma-separated list of project IDs (e.g. Lang,Math,Chart) or omit for all",
    )
    parser.add_argument(
        "--bugs",
        type=str,
        default=None,
        help="Comma-separated list of bug IDs (e.g. 1,2,5) or omit for all",
    )
    parser.add_argument(
        "--profile",
        choices=["scd4fl-2024"],
        default=None,
        help="Standard benchmark paper profile (Chart:1-26, Math:1-106, Lang:1-65, Time:1-27, Mockito:1-38, Closure:1-133)",
    )
    parser.add_argument(
        "--test-selection",
        choices=["relevant", "trigger", "all"],
        default="relevant",
        help="Test selection mode ('relevant' recommended for full scale)",
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        default=None,
        help="Optional limit on number of tests executed per bug (useful for quick smoke tests)",
    )
    parser.add_argument(
        "--instrument-scope",
        choices=["relevant", "modified", "all"],
        default="relevant",
        help="Code scope to instrument with P-predicates",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="Concurrent worker count (0 for automatic CPU/RAM calculation)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Per-test execution timeout in seconds",
    )
    parser.add_argument(
        "--cache",
        choices=["reuse", "refresh"],
        default="reuse",
        help="Instrumentation cache policy ('reuse' reuses existing traces, 'refresh' re-runs)",
    )
    parser.add_argument(
        "--rebuild-agent",
        action="store_true",
        help="Force re-compilation of Java agent JARs",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    log_level = getattr(LogLevel, args.log_level)
    reporter = ConsoleReporter(level=log_level, progress_enabled=True)

    print("=" * 80)
    print(f" Defects4J Automated Instrumentation & Dataset Generator (v{__version__})")
    print("=" * 80)

    # 1. Resolve JDK
    java_home = configure_java_home(args.java_home)
    if java_home:
        print(f"[*] Java Home: {java_home}")
    else:
        print("[!] Warning: JAVA_HOME not explicitly set; relying on system PATH.")

    # 2. Build or verify Java Agent
    print("[*] Ensuring Java agent JARs are built and ready...")
    agent = ensure_agent(
        asm_jar=None,
        java_home=java_home,
        reporter=reporter,
        rebuild=args.rebuild_agent,
    )
    print(f"[+] Java Agent JAR: {agent.jar}")
    print(f"[+] Java Runtime JAR: {agent.runtime_jar}")

    work_dir = args.work.resolve()
    cache_root = work_dir / "framework-cache"

    # 3. Locate Defects4J
    defects4j_target = args.defects4j
    if not defects4j_target:
        local_zip = SCRIPT_DIR / "defects4j-3.0.1.zip"
        if local_zip.is_file():
            defects4j_target = local_zip
        else:
            env_d4j = os.environ.get("DEFECTS4J_HOME") or os.environ.get("DEFECTS4J_PATH")
            if env_d4j and Path(env_d4j).exists():
                defects4j_target = Path(env_d4j)
            else:
                found = shutil.which("defects4j")
                if found:
                    defects4j_target = Path(found)
                else:
                    defects4j_target = local_zip

    if defects4j_target.suffix.lower() == ".zip" and not defects4j_target.is_file():
        print(f"[*] Defects4J archive not found at {defects4j_target}.")
        print("    Auto-downloading Defects4J v3.0.1 from GitHub...")

    distribution = prepare_defects4j(
        defects4j_target,
        cache_root=cache_root,
        setup_mode="auto",
        reporter=reporter,
    )
    executable = distribution.executable
    print(f"[+] Defects4J Executable: {executable}")

    # 4. Resolve Bug Targets
    projects_filter = {p.strip() for p in args.projects.split(",")} if args.projects else None
    bugs_filter = {int(b.strip()) for b in args.bugs.split(",")} if args.bugs else None

    bugs = resolve_bugs(
        executable,
        projects=projects_filter,
        bug_ids=bugs_filter,
        include_deprecated=False,
        profile=args.profile,
    )

    if not bugs:
        print("[-] No bugs resolved matching the given criteria.")
        sys.exit(1)

    print(f"[+] Total bugs to instrument: {len(bugs)}")
    for b in bugs[:10]:
        print(f"    - {b.key}")
    if len(bugs) > 10:
        print(f"    ... and {len(bugs) - 10} more.")

    # 5. Run Instrumentation Suite
    start_time = time.time()
    results = instrument_suite(
        executable=executable,
        work=work_dir,
        bugs=bugs,
        agent=agent,
        test_selection=args.test_selection,
        test_limit=args.test_limit,
        instrument_scope=args.instrument_scope,
        test_timeout=args.timeout,
        validate_fixed=False,
        jobs=args.jobs,
        cache_mode=args.cache,
        reporter=reporter,
    )
    elapsed = time.time() - start_time

    # 6. Summary
    print("\n" + "=" * 80)
    print(f" Instrumentation Complete in {elapsed:.2f} seconds!")
    print(f" Total Bug Versions Processed: {len(results)}")
    print(f" Consolidated Datasets Directory: {work_dir / 'datasets'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
