from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .progress import ConsoleReporter, LogLevel


class CommandError(RuntimeError):
    pass


def java_major() -> int | None:
    java = shutil.which("java")
    if not java:
        return None
    completed = subprocess.run(
        [java, "-version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    import re

    match = re.search(r'version "(?:1\.)?([0-9]+)', completed.stdout)
    return int(match.group(1)) if match else None


def configure_java_home(java_home: Path | None, *, required_major: int = 11) -> Path | None:
    if java_home is None:
        env_home = os.environ.get("JAVA_HOME")
        if env_home and Path(env_home).is_dir():
            java_home = Path(env_home)
        elif os.name == "nt":
            candidates = [
                Path(r"C:\Program Files\Eclipse Adoptium\jdk-11.0.33.10-hotspot"),
                *Path(r"C:\Program Files\Eclipse Adoptium").glob("jdk-11*"),
                *Path(r"C:\Program Files\Java").glob("jdk-11*"),
                *Path(r"C:\Program Files\Microsoft").glob("jdk-11*"),
            ]
            for c in candidates:
                if c.is_dir() and (c / "bin" / "java.exe").is_file():
                    java_home = c
                    break
        else:
            candidates = [
                Path("/usr/lib/jvm/java-11-openjdk-amd64"),
                Path("/usr/lib/jvm/java-11-openjdk"),
                *Path("/usr/lib/jvm").glob("java-11*"),
            ]
            for c in candidates:
                if c.is_dir() and (c / "bin" / "java").is_file():
                    java_home = c
                    break

    if java_home is not None:
        root = java_home.expanduser().resolve()
        suffix = ".exe" if os.name == "nt" else ""
        java = root / "bin" / f"java{suffix}"
        javac = root / "bin" / f"javac{suffix}"
        if not java.is_file() or not javac.is_file():
            raise CommandError(
                f"--java-home must contain Java executables under bin/: {root}"
            )
        os.environ["JAVA_HOME"] = str(root)
        os.environ["PATH"] = str(root / "bin") + os.pathsep + os.environ.get("PATH", "")
    major = java_major()
    if major is None:
        raise CommandError("java was not found. Defects4J 3.0.1 requires JDK 11.")
    if major != required_major:
        raise CommandError(
            f"Defects4J 3.0.1 requires Java {required_major}, but the active Java is {major}. "
            "Pass --java-home /path/to/jdk-11; no shell environment variable is required."
        )
    return java_home


def defects4j_root(executable: Path) -> Path | None:
    """Return the distribution root for framework/bin/defects4j."""
    path = executable.expanduser().resolve()
    if path.name != "defects4j" or path.parent.name != "bin" or path.parent.parent.name != "framework":
        return None
    return path.parents[2]


def defects4j_environment(
    executable: Path,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an execution environment that exposes cache-local Perl modules.

    Defects4J's Perl dependencies are installed below the extracted framework
    rather than in a user or system-wide Perl tree. Every Defects4J invocation
    receives the matching library path automatically.
    """
    env = (os.environ.copy() if base is None else base.copy())
    root = defects4j_root(executable)
    if root is None:
        return env
    library = root / ".efl-perl5" / "lib" / "perl5"
    if not library.is_dir():
        return env
    current = env.get("PERL5LIB", "")
    entries = [str(library)]
    if current:
        entries.append(current)
    env["PERL5LIB"] = os.pathsep.join(entries)
    return env


def resolve_defects4j(
    value: Path | None,
    *,
    cache_root: Path | None = None,
    setup_mode: str = "auto",
    reporter: ConsoleReporter | None = None,
) -> Path:
    if value is None:
        package_root = Path(__file__).resolve().parents[1]
        local_candidates = [
            package_root / "defects4j-3.0.1.zip",
            Path.cwd() / "defects4j-3.0.1.zip",
            package_root / "defects4j",
            Path.cwd() / "defects4j",
        ]
        for candidate in local_candidates:
            if candidate.exists():
                value = candidate
                break

    if value is None:
        env_d4j = os.environ.get("DEFECTS4J_HOME") or os.environ.get("DEFECTS4J_PATH")
        if env_d4j and Path(env_d4j).exists():
            value = Path(env_d4j)
        else:
            found = shutil.which("defects4j")
            if not found:
                raise CommandError(
                    "Defects4J was not found. Pass --defects4j /path/to/defects4j-3.0.1.zip, "
                    "/path/to/defects4j, or framework/bin/defects4j."
                )
            value = Path(found)
    from .framework import prepare_defects4j

    prepared = prepare_defects4j(
        value,
        cache_root=cache_root,
        setup_mode=setup_mode,
        reporter=reporter,
    )
    if reporter:
        version = prepared.version or "unknown"
        reporter.log(
            LogLevel.INFO,
            f"Defects4J framework ready: {prepared.root} (version={version}, initialized={prepared.initialized})",
        )
    return prepared.executable


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
    reporter: ConsoleReporter | None = None,
    description: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if reporter and description:
        reporter.log(LogLevel.DEBUG, description)
        reporter.log(LogLevel.DEBUG, "Command: " + " ".join(command))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"Command timed out after {timeout}s: {' '.join(command)}") from exc
    if check and completed.returncode != 0:
        tail = completed.stderr[-4000:] or completed.stdout[-4000:]
        raise CommandError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}\n{tail}"
        )
    return completed


def d4j(
    executable: Path,
    args: Iterable[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
    reporter: ConsoleReporter | None = None,
    description: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [str(executable), *list(args)]
    if os.name == "nt" and not str(executable).lower().endswith((".exe", ".bat", ".cmd")):
        perl = shutil.which("perl") or r"C:\Program Files\Git\usr\bin\perl.exe"
        if os.path.isfile(perl):
            cmd = [perl, str(executable), *list(args)]
    return run_command(
        cmd,
        cwd=cwd,
        env=defects4j_environment(executable, env),
        timeout=timeout,
        check=check,
        reporter=reporter,
        description=description,
    )


def export_property(executable: Path, worktree: Path, property_name: str) -> str:
    completed = d4j(executable, ["export", "-w", str(worktree), "-p", property_name])
    return completed.stdout.strip()


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.replace(";", "\n").splitlines() if line.strip()]


def split_paths(value: str, worktree: Path) -> list[Path]:
    pieces: list[str] = []
    for line in value.splitlines():
        pieces.extend(item for item in line.split(os.pathsep) if item)
    result: list[Path] = []
    for item in pieces:
        path = Path(item.strip())
        if not path.is_absolute():
            path = worktree / path
        result.append(path.resolve())
    return result


def query_bug_ids(executable: Path, project: str, include_deprecated: bool) -> list[int]:
    args = ["query", "-p", project]
    if include_deprecated:
        args.append("-A")
    completed = d4j(executable, args)
    rows = list(csv.reader(completed.stdout.splitlines()))
    values: list[int] = []
    for row in rows:
        if not row:
            continue
        try:
            values.append(int(row[0].strip()))
        except ValueError:
            continue
    return sorted(set(values))
