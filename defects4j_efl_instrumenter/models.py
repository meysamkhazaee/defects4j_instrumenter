from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BugRef:
    project: str
    bug_id: int

    @property
    def key(self) -> str:
        return f"{self.project}/v{self.bug_id}"


@dataclass(frozen=True)
class AgentBuild:
    jar: Path
    mode: str

    @property
    def runtime_jar(self) -> Path:
        return self.jar.parent / "defects4j-efl-runtime.jar"

    @property
    def java_options(self) -> list[str]:
        if self.mode == "jdk-internal":
            return ["--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED"]
        return []


@dataclass
class VersionMetadata:
    project: str
    bug_id: int
    buggy_root: Path
    fixed_root: Path
    source_dirs: list[Path] = field(default_factory=list)
    class_dirs: list[Path] = field(default_factory=list)
    test_source_dirs: list[Path] = field(default_factory=list)
    test_class_dirs: list[Path] = field(default_factory=list)
    classes_modified: list[str] = field(default_factory=list)
    classes_relevant: list[str] = field(default_factory=list)
    tests_all_classes: list[str] = field(default_factory=list)
    tests_relevant_classes: list[str] = field(default_factory=list)
    tests_trigger_methods: list[str] = field(default_factory=list)
    cp_compile: str = ""
    cp_test: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("buggy_root", "fixed_root"):
            payload[key] = str(payload[key])
        for key in ("source_dirs", "class_dirs", "test_source_dirs", "test_class_dirs"):
            payload[key] = [str(value) for value in payload[key]]
        return payload


@dataclass
class TestRun:
    test: str
    result: str
    return_code: int = 0
    timed_out: bool = False
    duration_seconds: float = 0.0
    trace_file: Path | None = None
    trace_count: int = 0
    stderr_tail: str = ""
    fixed_result: str | None = None
    cache_hit: bool = False

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trace_file"] = str(self.trace_file) if self.trace_file else None
        return payload
