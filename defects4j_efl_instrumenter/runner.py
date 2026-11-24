from __future__ import annotations

import concurrent.futures
import csv
import json
import os
import shutil
import struct
import subprocess
import time
from pathlib import Path
from typing import Iterable

from . import __version__
from .agent import ensure_agent, java_command, java_tool_options
from .commands import CommandError, d4j, query_bug_ids, run_command
from .metadata import collect_metadata
from .models import AgentBuild, BugRef, TestRun, VersionMetadata
from .patch import source_changes
from .progress import ConsoleReporter, LogLevel
from .trace import (
    merge_trace_directory,
    resolve_fault_predicates,
    safe_test_id,
    write_detailed_summary,
    write_efl_input,
    write_json,
    write_standard_matrix_dataset,
    write_tagged_matrix_dataset,
)
from .cache_support import fingerprint, hash_file, validate_cache_manifest, write_cache_manifest


PAPER_PROFILE: dict[str, range] = {
    "Chart": range(1, 27),
    "Math": range(1, 107),
    "Lang": range(1, 66),
    "Time": range(1, 28),
    "Mockito": range(1, 39),
    "Closure": range(1, 134),
}


def discover_projects(executable: Path) -> list[str]:
    completed = d4j(executable, ["pids"])
    return sorted(line.strip() for line in completed.stdout.splitlines() if line.strip())


def resolve_bugs(
    executable: Path,
    *,
    projects: set[str] | None,
    bug_ids: set[int] | None,
    include_deprecated: bool,
    profile: str | None,
) -> list[BugRef]:
    if profile == "scd4fl-2024":
        selected_projects = {p.lower() for p in projects} if projects else None
        refs: list[BugRef] = []
        missing: list[str] = []
        for project, values in PAPER_PROFILE.items():
            if selected_projects and project.lower() not in selected_projects:
                continue
            selected_values = [value for value in values if not bug_ids or value in bug_ids]
            available = (
                set(query_bug_ids(executable, project, include_deprecated=True))
                if executable.is_file()
                else set(selected_values)
            )
            for bug_id in selected_values:
                if bug_id in available:
                    refs.append(BugRef(project, bug_id))
                else:
                    missing.append(f"{project}-{bug_id}")
        if missing:
            preview = ", ".join(missing[:20])
            suffix = " ..." if len(missing) > 20 else ""
            raise RuntimeError(
                "The installed Defects4J distribution does not contain every bug required by "
                f"the scd4fl-2024 profile: {preview}{suffix}"
            )
        return refs

    available = discover_projects(executable)
    selected = [p for p in available if not projects or p.lower() in {v.lower() for v in projects}]
    refs: list[BugRef] = []
    for project in selected:
        values = query_bug_ids(executable, project, include_deprecated)
        if bug_ids:
            values = [value for value in values if value in bug_ids]
        refs.extend(BugRef(project, value) for value in values)
    return refs


def _valid_json(path: Path) -> bool:
    try:
        return path.is_file() and bool(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def result_root(work: Path, bug: BugRef, test_set: str) -> Path:
    return work / "results" / bug.project / f"v{bug.bug_id}" / test_set


def _dataset_name(bug: BugRef) -> str:
    return f"cmp.v0.v{bug.bug_id}.{bug.project}.csv"


def _result_cache_status(root: Path, bug: BugRef, expected_fingerprint: str | None = None) -> tuple[bool, str]:
    required = [
        root / "complete.json",
        root / _dataset_name(bug),
        root / "source_map.csv",
        root / "source_changes.json",
        root / "metadata.json",
        root / "tests.jsonl",
    ]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        return False, "missing " + ", ".join(missing)
    if not _valid_json(root / "complete.json"):
        return False, "invalid complete.json"
    if (root / _dataset_name(bug)).stat().st_size == 0:
        return False, "empty EFL input"
    if expected_fingerprint is not None:
        valid, reason = validate_cache_manifest(root, expected_fingerprint)
        if not valid:
            return False, reason
    return True, "complete"


def _checkout(
    executable: Path,
    bug: BugRef,
    suffix: str,
    destination: Path,
    *,
    reporter: ConsoleReporter,
    refresh: bool,
) -> None:
    marker = destination / ".efl_checkout.json"
    expected = {"project": bug.project, "version": f"{bug.bug_id}{suffix}"}
    if not refresh and marker.is_file():
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == expected:
                reporter.log(LogLevel.DEBUG, f"[CACHE HIT] {bug.key}/{suffix} checkout")
                return
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    reporter.log(LogLevel.INFO, f"[CHECKOUT] {bug.key}/{suffix}")
    d4j(
        executable,
        ["checkout", "-p", bug.project, "-v", f"{bug.bug_id}{suffix}", "-w", str(destination)],
        reporter=reporter,
        description=f"Checking out {bug.key}/{suffix}",
    )
    write_json(marker, expected)


def _compile(
    executable: Path,
    bug: BugRef,
    suffix: str,
    worktree: Path,
    *,
    reporter: ConsoleReporter,
    refresh: bool,
) -> None:
    marker = worktree / ".efl_compile.json"
    if not refresh and _valid_json(marker):
        reporter.log(LogLevel.DEBUG, f"[CACHE HIT] {bug.key}/{suffix} compile")
        return
    reporter.log(LogLevel.INFO, f"[COMPILE] {bug.key}/{suffix}")
    d4j(
        executable,
        ["compile", "-w", str(worktree)],
        reporter=reporter,
        description=f"Compiling {bug.key}/{suffix}",
    )
    write_json(marker, {"project": bug.project, "version": f"{bug.bug_id}{suffix}", "compiled": True})


def _write_lines(path: Path, values: Iterable[Path | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in values), encoding="utf-8")


def _instrumentation_filter(metadata: VersionMetadata, scope: str) -> list[str]:
    if scope == "all":
        return []
    if scope == "modified":
        return metadata.classes_modified
    values = metadata.classes_relevant or metadata.classes_modified
    return values


def _create_source_map(
    metadata: VersionMetadata,
    result: Path,
    agent: AgentBuild,
    scope: str,
    reporter: ConsoleReporter,
) -> None:
    bins_file = result / "instrumentation" / "class_dirs.txt"
    filter_file = result / "instrumentation" / "classes.txt"
    mapping = result / "instrumentation" / "mapping.tsv"
    source_map = result / "source_map.csv"
    _write_lines(bins_file, metadata.class_dirs)
    selected = _instrumentation_filter(metadata, scope)
    if selected:
        _write_lines(filter_file, selected)
        filter_arg = str(filter_file)
    else:
        filter_arg = "-"
    source_root = ""
    if metadata.source_dirs:
        try:
            source_root = metadata.source_dirs[0].relative_to(metadata.buggy_root).as_posix()
        except ValueError:
            source_root = metadata.source_dirs[0].as_posix()
    command = [
        *java_command(agent),
        "org.efl.defects4j.tools.ClassScanner",
        str(bins_file),
        filter_arg,
        source_root,
        str(mapping),
        str(source_map),
    ]
    run_command(command, reporter=reporter, description=f"Building source map for {metadata.project}/v{metadata.bug_id}")
    if not mapping.is_file() or mapping.stat().st_size == 0:
        raise RuntimeError(
            f"No executable predicates were mapped for {metadata.project}/v{metadata.bug_id}. "
            "Try --instrument-scope all."
        )


def _enumerate_tests(
    metadata: VersionMetadata,
    result: Path,
    agent: AgentBuild,
    selection: str,
    limit: int | None,
    reporter: ConsoleReporter,
) -> list[str]:
    triggers = list(dict.fromkeys(metadata.tests_trigger_methods))
    if selection == "trigger":
        tests = triggers
    else:
        allowed = metadata.tests_all_classes if selection == "all" else metadata.tests_relevant_classes
        bins_file = result / "instrumentation" / "test_class_dirs.txt"
        classes_file = result / "instrumentation" / "test_classes.txt"
        output = result / "instrumentation" / "test_methods.txt"
        _write_lines(bins_file, metadata.test_class_dirs)
        _write_lines(classes_file, allowed)
        run_command(
            [
                *java_command(agent),
                "org.efl.defects4j.tools.TestEnumerator",
                str(bins_file),
                str(classes_file),
                str(output),
            ],
            reporter=reporter,
            description=f"Enumerating tests for {metadata.project}/v{metadata.bug_id}",
        )
        enumerated = [line.strip() for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
        tests = list(dict.fromkeys([*triggers, *enumerated]))
    if limit is not None:
        tests = tests[: max(0, limit)]
    return tests


def _test_result(worktree: Path, return_code: int, timed_out: bool) -> str:
    if timed_out:
        return "U"
    failing = worktree / "failing_tests"
    if failing.is_file() and failing.read_text(encoding="utf-8", errors="replace").strip():
        return "F"
    return "T" if return_code == 0 else "U"


def _load_cached_test(cache_json: Path, trace_file: Path) -> TestRun | None:
    if not cache_json.is_file() or not trace_file.is_file():
        return None
    try:
        payload = json.loads(cache_json.read_text(encoding="utf-8"))
        return TestRun(
            test=str(payload["test"]),
            result=str(payload["result"]),
            return_code=int(payload["return_code"]),
            timed_out=bool(payload["timed_out"]),
            duration_seconds=float(payload["duration_seconds"]),
            trace_file=trace_file,
            trace_count=int(payload["trace_count"]),
            stderr_tail=str(payload.get("stderr_tail", "")),
            fixed_result=payload.get("fixed_result"),
            cache_hit=True,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _run_uninstrumented_test(
    executable: Path,
    worktree: Path,
    test: str,
    timeout: float,
) -> str:
    failing = worktree / "failing_tests"
    failing.unlink(missing_ok=True)
    try:
        completed = d4j(
            executable,
            ["test", "-w", str(worktree), "-t", test],
            timeout=timeout,
            check=False,
        )
        return _test_result(worktree, completed.returncode, False)
    except CommandError:
        return "U"


def _run_test(
    executable: Path,
    metadata: VersionMetadata,
    result: Path,
    agent: AgentBuild,
    test: str,
    *,
    timeout: float,
    validate_fixed: bool,
    cache_mode: str,
    reporter: ConsoleReporter,
) -> TestRun:
    test_root = result / "tests" / safe_test_id(test)
    cache_json = test_root / "complete.json"
    trace_file = test_root / "trace.bin"
    if cache_mode == "reuse":
        cached = _load_cached_test(cache_json, trace_file)
        if cached:
            reporter.log(LogLevel.DEBUG, f"[CACHE HIT] {metadata.project}/v{metadata.bug_id} {test}")
            return cached
    if test_root.exists():
        shutil.rmtree(test_root)
    raw = test_root / "raw"
    raw.mkdir(parents=True)
    properties = test_root / "agent.properties"
    mapping = result / "instrumentation" / "mapping.tsv"
    properties.write_text(
        f"mapping={mapping.as_posix()}\noutput_dir={raw.as_posix()}\ndebug=false\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["TZ"] = "America/Los_Angeles"
    previous = env.get("JAVA_TOOL_OPTIONS", "").strip()
    options = java_tool_options(agent, properties)
    env["JAVA_TOOL_OPTIONS"] = (previous + " " + options).strip()
    failing = metadata.buggy_root / "failing_tests"
    failing.unlink(missing_ok=True)
    started = time.monotonic()
    timed_out = False
    stderr_tail = ""
    return_code = 124
    try:
        completed = d4j(
            executable,
            ["test", "-w", str(metadata.buggy_root), "-t", test],
            env=env,
            timeout=timeout,
            check=False,
        )
        return_code = completed.returncode
        stderr_tail = completed.stderr[-4000:]
    except CommandError as exc:
        timed_out = "timed out" in str(exc).lower()
        stderr_tail = str(exc)[-4000:]
    duration = time.monotonic() - started
    result_label = _test_result(metadata.buggy_root, return_code, timed_out)
    trace_count = merge_trace_directory(raw, trace_file)
    fixed_result = None
    if validate_fixed:
        fixed_result = _run_uninstrumented_test(executable, metadata.fixed_root, test, timeout)
        if fixed_result != "T":
            result_label = "U"
    run = TestRun(
        test=test,
        result=result_label,
        return_code=return_code,
        timed_out=timed_out,
        duration_seconds=duration,
        trace_file=trace_file,
        trace_count=trace_count,
        stderr_tail=stderr_tail,
        fixed_result=fixed_result,
    )
    write_json(cache_json, run.to_json())
    shutil.rmtree(raw, ignore_errors=True)
    return run


def _test_set_key(selection: str, limit: int | None) -> str:
    base = "full" if selection == "all" else selection
    return base if limit is None else f"{base}-first-{limit}"


def instrument_bug(
    executable: Path,
    work: Path,
    bug: BugRef,
    agent: AgentBuild,
    *,
    test_selection: str,
    test_limit: int | None,
    instrument_scope: str,
    test_timeout: float,
    validate_fixed: bool,
    cache_mode: str,
    refresh_checkouts: bool,
    keep_checkouts: bool,
    reporter: ConsoleReporter,
) -> Path:
    test_set = _test_set_key(test_selection, test_limit)
    output = result_root(work, bug, test_set)
    cache_options = {
        "bug": bug.key, "test_selection": test_selection, "test_limit": test_limit,
        "instrument_scope": instrument_scope, "test_timeout": test_timeout,
        "validate_fixed": validate_fixed, "agent_mode": agent.mode,
    }
    cache_fingerprint = fingerprint({
        "release": __version__, "options": cache_options,
        "defects4j_executable_sha256": hash_file(executable),
        "agent_sha256": hash_file(agent.jar),
    })
    cached, reason = _result_cache_status(output, bug, cache_fingerprint)
    if cache_mode == "reuse" and cached:
        reporter.log(LogLevel.INFO, f"[CACHE HIT] {bug.key}/{test_set} instrumentation")
        return output
    reporter.log(LogLevel.INFO, f"[CACHE {'REFRESH' if cache_mode == 'refresh' else 'MISS'}] {bug.key}/{test_set}: {reason}")
    if cache_mode == "refresh" and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    checkout_root = work / "checkouts" / bug.project / f"v{bug.bug_id}"
    buggy = checkout_root / "buggy"
    fixed = checkout_root / "fixed"
    _checkout(executable, bug, "b", buggy, reporter=reporter, refresh=refresh_checkouts)
    _checkout(executable, bug, "f", fixed, reporter=reporter, refresh=refresh_checkouts)
    _compile(executable, bug, "b", buggy, reporter=reporter, refresh=refresh_checkouts)
    if validate_fixed:
        _compile(executable, bug, "f", fixed, reporter=reporter, refresh=refresh_checkouts)

    metadata = collect_metadata(executable, bug.project, bug.bug_id, buggy, fixed)
    write_json(output / "metadata.json", {
        **metadata.to_json(),
        "benchmark": "Defects4J",
        "test_selection": test_selection,
        "test_limit": test_limit,
        "instrument_scope": instrument_scope,
        "validate_fixed": validate_fixed,
        "agent_mode": agent.mode,
    })
    _create_source_map(metadata, output, agent, instrument_scope, reporter)
    changes = []
    for buggy_source in metadata.source_dirs:
        try:
            relative_source = buggy_source.relative_to(buggy)
        except ValueError:
            relative_source = Path()
        fixed_source = fixed / relative_source
        if fixed_source.exists():
            changes.extend(
                source_changes(
                    buggy_source,
                    fixed_source,
                    source_prefix=relative_source.as_posix() if str(relative_source) != "." else "",
                )
            )
    if not changes:
        changes = source_changes(buggy, fixed)
    write_json(output / "source_changes.json", changes)
    tests = _enumerate_tests(metadata, output, agent, test_selection, test_limit, reporter)
    if not tests:
        raise RuntimeError(f"No test methods were discovered for {bug.key}")
    reporter.log(LogLevel.INFO, f"{bug.key}: executing {len(tests)} test method(s)")

    runs: list[TestRun] = []
    reporter.progress(0, len(tests), label=f"{bug.key} tests", detail="queued")
    for index, test in enumerate(tests, start=1):
        run = _run_test(
            executable,
            metadata,
            output,
            agent,
            test,
            timeout=test_timeout,
            validate_fixed=validate_fixed,
            cache_mode=cache_mode,
            reporter=reporter,
        )
        runs.append(run)
        detail = f"{test} [{run.result}, trace={run.trace_count}]"
        reporter.progress(index, len(tests), label=f"{bug.key} tests", detail=detail)

    usable = [run for run in runs if run.result in {"T", "F"} and run.trace_count > 0]
    excluded = [run for run in runs if run not in usable]
    if not any(run.result == "F" for run in usable):
        raise RuntimeError(
            f"{bug.key} produced no failing traced tests. Try --instrument-scope all, "
            "--test-selection all, or inspect excluded_tests.csv."
        )
    efl_input = output / _dataset_name(bug)
    write_efl_input(efl_input, usable)

    # Resolve fault markers & produce standard Siemens-style matrix and tagged datasets
    source_map_file = output / "source_map.csv"
    source_changes_file = output / "source_changes.json"
    fault_predicates = resolve_fault_predicates(source_map_file, source_changes_file)

    dataset_txt = output / f"v{bug.bug_id}_dataset.txt"
    tagged_txt = output / f"v{bug.bug_id}_tagged.txt"
    detailed_json = output / f"v{bug.bug_id}_detailed.json"

    write_standard_matrix_dataset(dataset_txt, usable)
    tag_info = write_tagged_matrix_dataset(tagged_txt, usable, fault_predicates)
    write_detailed_summary(
        detailed_json,
        project=bug.project,
        bug_id=bug.bug_id,
        runs=usable,
        fault_predicates=fault_predicates,
        tag_info=tag_info,
    )

    # Also mirror into a unified datasets directory: work/datasets/<project>/
    unified_datasets_dir = work / "datasets" / bug.project
    unified_datasets_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(dataset_txt, unified_datasets_dir / f"v{bug.bug_id}_dataset.txt")
        shutil.copy2(tagged_txt, unified_datasets_dir / f"v{bug.bug_id}_tagged.txt")
        shutil.copy2(detailed_json, unified_datasets_dir / f"v{bug.bug_id}_detailed.json")
        shutil.copy2(efl_input, unified_datasets_dir / _dataset_name(bug))
    except Exception:
        pass

    with (output / "tests.jsonl").open("w", encoding="utf-8") as stream:
        for run in runs:
            stream.write(json.dumps(run.to_json(), ensure_ascii=False) + "\n")
    with (output / "excluded_tests.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["test", "result", "fixed_result", "return_code", "timed_out", "trace_count", "reason"])
        for run in excluded:
            reason = "empty_trace" if run.trace_count == 0 else "invalid_or_fixed_failure"
            writer.writerow([run.test, run.result, run.fixed_result or "", run.return_code, run.timed_out, run.trace_count, reason])
    stats = {
        "tests_discovered": len(runs),
        "tests_usable": len(usable),
        "tests_excluded": len(excluded),
        "passing": sum(run.result == "T" for run in usable),
        "failing": sum(run.result == "F" for run in usable),
        "total_trace_events": sum(run.trace_count for run in usable),
        "maximum_trace_events": max((run.trace_count for run in usable), default=0),
        "minimum_trace_events": min((run.trace_count for run in usable), default=0),
    }
    write_json(output / "trace_statistics.json", stats)
    write_json(output / "complete.json", {"complete": True, "bug": bug.key, **stats})
    write_cache_manifest(
        output, fp=cache_fingerprint, options=cache_options,
        outputs=[output / "complete.json", efl_input, output / "source_map.csv", output / "source_changes.json", output / "metadata.json", output / "tests.jsonl"],
    )
    reporter.log(LogLevel.INFO, f"[INSTRUMENTED] {bug.key}/{test_set}: {efl_input}")

    if not keep_checkouts:
        shutil.rmtree(checkout_root, ignore_errors=True)
    return output


def _available_memory_bytes() -> int | None:
    """Best-effort Linux memory availability used only for auto worker sizing."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def resolve_instrument_jobs(jobs: int) -> tuple[int, str]:
    """Resolve bug-level Defects4J concurrency.

    jobs > 0 is an explicit worker count. jobs == 0 enables a conservative
    auto mode. Tests inside one bug remain sequential because Defects4J uses
    mutable files/build outputs inside a checkout; different bugs have isolated
    checkout/result directories and can be processed safely in parallel.
    """
    if jobs < 0:
        raise ValueError("instrument jobs must be >= 0 (0 means auto)")
    if jobs > 0:
        return jobs, f"explicit={jobs}"

    cpu_count = os.cpu_count() or 1
    cpu_workers = max(1, cpu_count // 2)
    memory = _available_memory_bytes()
    if memory is None:
        memory_workers = 4
        memory_detail = "memory=unknown"
    else:
        # Compilation/test JVMs vary substantially across Defects4J projects.
        # Reserve ~3 GiB per active bug worker to avoid turning parallelism into
        # swap thrashing or OOM kills on Closure/Math/Jackson-style projects.
        per_worker = 3 * 1024**3
        memory_workers = max(1, memory // per_worker)
        memory_detail = f"available_memory_gib={memory / 1024**3:.1f}"
    resolved = max(1, min(8, cpu_workers, memory_workers))
    return resolved, f"auto cpu={cpu_count}, {memory_detail}, cap=8"


def instrument_suite(
    executable: Path,
    work: Path,
    bugs: list[BugRef],
    *,
    agent: AgentBuild | None = None,
    asm_jar: Path | None = None,
    rebuild_agent: bool = False,
    test_selection: str = "relevant",
    test_limit: int | None = None,
    instrument_scope: str = "relevant",
    test_timeout: float = 300.0,
    validate_fixed: bool = False,
    cache_mode: str = "reuse",
    refresh_checkouts: bool = False,
    keep_checkouts: bool = False,
    jobs: int = 4,
    reporter: ConsoleReporter | None = None,
) -> list[Path]:
    if not bugs:
        raise RuntimeError("No Defects4J bugs matched the selection")
    if reporter is None:
        reporter = ConsoleReporter()
    if agent is None:
        agent = ensure_agent(asm_jar=asm_jar, reporter=reporter, rebuild=rebuild_agent)
    work = work.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    max_workers, jobs_detail = resolve_instrument_jobs(jobs)
    reporter.log(
        LogLevel.INFO,
        f"Defects4J instrumentation: bugs={len(bugs)}, jobs={max_workers} ({jobs_detail})",
    )
    reporter.progress(0, len(bugs), label="Defects4J bugs instrumented", detail="queued")
    completed: list[Path] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                instrument_bug,
                executable,
                work,
                bug,
                agent,
                test_selection=test_selection,
                test_limit=test_limit,
                instrument_scope=instrument_scope,
                test_timeout=test_timeout,
                validate_fixed=validate_fixed,
                cache_mode=cache_mode,
                refresh_checkouts=refresh_checkouts,
                keep_checkouts=keep_checkouts,
                reporter=reporter,
            ): bug
            for bug in bugs
        }
        done = 0
        for future in concurrent.futures.as_completed(future_map):
            bug = future_map[future]
            done += 1
            try:
                completed.append(future.result())
                detail = bug.key
            except Exception as exc:
                failures.append(f"{bug.key}: {exc}")
                reporter.log(LogLevel.ERROR, f"{bug.key}: {exc}")
                detail = f"failed: {bug.key}"
            reporter.progress(done, len(bugs), label="Defects4J bugs instrumented", detail=detail)
    if failures:
        (work / "instrumentation_failures.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")
        raise RuntimeError("Defects4J instrumentation failed:\n" + "\n".join(failures))
    return sorted(completed)


def inspect_results(work_or_results: Path) -> list[dict[str, object]]:
    root = work_or_results.expanduser().resolve()
    results = root / "results" if (root / "results").is_dir() else root
    payload: list[dict[str, object]] = []
    for csv_path in sorted(results.glob("*/v*/*/cmp.v0.v*.*.csv")):
        version_root = csv_path.parent
        complete = _valid_json(version_root / "complete.json")
        payload.append(
            {
                "project": version_root.parent.parent.name,
                "version": int(version_root.parent.name.lstrip("v")),
                "test_set": version_root.name,
                "input": str(csv_path),
                "complete": complete,
            }
        )
    return payload
