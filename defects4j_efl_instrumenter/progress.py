from __future__ import annotations

import enum
import shutil
import sys
import threading
from dataclasses import dataclass, field
from typing import TextIO


class LogLevel(enum.IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40

    @classmethod
    def parse(cls, value: str) -> "LogLevel":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            allowed = ", ".join(item.name for item in cls)
            raise ValueError(f"invalid log level {value!r}; expected one of: {allowed}") from exc


@dataclass
class ConsoleReporter:
    level: LogLevel = LogLevel.INFO
    progress_enabled: bool = True
    width: int = 32
    stream: TextIO = sys.stdout
    error_stream: TextIO = sys.stderr
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _active_progress: bool = field(default=False, init=False, repr=False)

    def enabled_for(self, level: LogLevel) -> bool:
        return level >= self.level

    def log(self, level: LogLevel, message: str) -> None:
        if not self.enabled_for(level):
            return
        target = self.error_stream if level >= LogLevel.ERROR else self.stream
        with self._lock:
            self._finish_active_progress_locked()
            print(f"[{level.name}] {message}", file=target, flush=True)

    def progress(
        self,
        current: int,
        total: int,
        *,
        label: str,
        detail: str = "",
        final: bool | None = None,
    ) -> None:
        if not self.progress_enabled:
            return
        total = max(0, total)
        current = max(0, min(current, total)) if total else max(0, current)
        completed = current >= total if total else bool(final)
        if final is not None:
            completed = final

        fraction = (current / total) if total else 0.0
        filled = min(self.width, int(round(fraction * self.width)))
        bar = "#" * filled + "-" * (self.width - filled)
        percent = fraction * 100.0
        suffix = f" {detail}" if detail else ""
        line = f"[{bar}] {percent:6.2f}% {current}/{total} {label}{suffix}"

        with self._lock:
            interactive = bool(getattr(self.stream, "isatty", lambda: False)())
            if interactive:
                terminal_width = shutil.get_terminal_size((120, 20)).columns
                visible = line[: max(1, terminal_width - 1)]
                padding = " " * max(0, terminal_width - 1 - len(visible))
                print(f"\r{visible}{padding}", end="", file=self.stream, flush=True)
                self._active_progress = True
                if completed:
                    print(file=self.stream, flush=True)
                    self._active_progress = False
            else:
                print(line, file=self.stream, flush=True)

    def _finish_active_progress_locked(self) -> None:
        if self._active_progress:
            print(file=self.stream, flush=True)
            self._active_progress = False

    def finish(self) -> None:
        with self._lock:
            self._finish_active_progress_locked()
