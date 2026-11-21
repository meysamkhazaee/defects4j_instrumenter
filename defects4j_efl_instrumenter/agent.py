from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .commands import CommandError, java_major, run_command
from .models import AgentBuild
from .progress import ConsoleReporter, LogLevel


def agent_source_root() -> Path:
    return Path(__file__).resolve().parents[1] / "java-agent"


def ensure_agent(
    *,
    asm_jar: Path | None,
    reporter: ConsoleReporter,
    rebuild: bool = False,
    java_home: Path | None = None,
) -> AgentBuild:
    root = agent_source_root()
    jar = root / "build" / "defects4j-efl-agent.jar"
    runtime_jar = root / "build" / "defects4j-efl-runtime.jar"
    mode_file = root / "build" / "build-mode.txt"
    java_version_file = root / "build" / "build-java-version.txt"
    current_java = java_major()
    stale_internal_build = False
    if mode_file.is_file() and mode_file.read_text(encoding="utf-8").strip() == "jdk-internal":
        recorded_java: int | None = None
        if java_version_file.is_file():
            import re

            match = re.search(
                r'version "(?:1\.)?([0-9]+)',
                java_version_file.read_text(encoding="utf-8", errors="replace"),
            )
            recorded_java = int(match.group(1)) if match else None
        stale_internal_build = current_java is None or current_java < 11 or recorded_java != current_java
    if rebuild or stale_internal_build or not jar.is_file() or not runtime_jar.is_file() or not mode_file.is_file():
        command = [sys.executable, str(root / "build.py")]
        if asm_jar:
            command += ["--asm-jar", str(asm_jar.expanduser().resolve())]
        if java_home:
            command += ["--java-home", str(java_home.expanduser().resolve())]
        run_command(command, cwd=root, reporter=reporter, description="Building Defects4J EFL Java agent")
    mode = mode_file.read_text(encoding="utf-8").strip()
    if mode not in {"jdk-internal", "external-asm"}:
        raise CommandError(f"Unknown Java agent build mode: {mode}")
    if mode == "jdk-internal" and (current_java is None or current_java < 11):
        raise CommandError(
            f"The JDK-internal Java agent requires Java 11 or newer, but active Java is {current_java}."
        )
    reporter.log(LogLevel.INFO, f"Defects4J Java agent: {jar} ({mode})")
    return AgentBuild(jar=jar, mode=mode)


def java_tool_options(agent: AgentBuild, properties_file: Path) -> str:
    values = [*agent.java_options, f"-javaagent:{agent.jar}={properties_file}"]
    for value in values:
        if any(ch.isspace() for ch in value):
            raise CommandError(
                "Defects4J tracing paths must not contain whitespace because JAVA_TOOL_OPTIONS "
                f"cannot represent this option safely: {value}"
            )
    return " ".join(values)


def java_command(agent: AgentBuild) -> list[str]:
    java = shutil.which("java")
    if not java:
        raise CommandError("java was not found in PATH")
    return [java, *agent.java_options, "-cp", str(agent.jar)]
