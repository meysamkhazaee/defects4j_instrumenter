from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .commands import CommandError, defects4j_environment
from .progress import ConsoleReporter, LogLevel


@dataclass(frozen=True)
class Defects4JFramework:
    root: Path
    executable: Path
    initialized: bool
    version: str | None = None
    archive_sha256: str | None = None


_REQUIRED_EXECUTABLES = (
    "git",
    "svn",
    "perl",
    "cpanm",
    "curl",
    "unzip",
)


def _log(reporter: ConsoleReporter | None, level: LogLevel, message: str) -> None:
    if reporter:
        reporter.log(level, message)
    else:
        print(f"[{level.name}] {message}", file=sys.stderr, flush=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return value or "defects4j"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _extract_zip(archive: Path, destination: Path, reporter: ConsoleReporter | None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.extract-", dir=destination.parent))
    _log(reporter, LogLevel.INFO, f"[DEFECTS4J EXTRACT] {archive} -> {destination}")
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                posix = PurePosixPath(member.filename)
                if posix.is_absolute() or ".." in posix.parts:
                    raise CommandError(f"Unsafe path in Defects4J archive: {member.filename}")
                mode = (member.external_attr >> 16) & 0xFFFF
                target = (temporary / Path(*posix.parts)).resolve()
                if not _is_within(target, temporary.resolve()):
                    raise CommandError(f"Unsafe extraction target in Defects4J archive: {member.filename}")
                if stat.S_ISLNK(mode):
                    link_value = bundle.read(member).decode("utf-8", errors="strict")
                    link_path = PurePosixPath(link_value)
                    if link_path.is_absolute():
                        raise CommandError(f"Unsafe absolute symlink in Defects4J archive: {member.filename}")
                    resolved_link = (target.parent / Path(*link_path.parts)).resolve()
                    if not _is_within(resolved_link, temporary.resolve()):
                        raise CommandError(f"Unsafe symlink target in Defects4J archive: {member.filename} -> {link_value}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(link_value)
                elif member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    if mode:
                        target.chmod(mode & 0o777)
                if reporter and total > 0 and (index == total or index % max(1, total // 20) == 0):
                    reporter.progress(index, total, label="Defects4J archive extracted", detail=member.filename)

        candidates = sorted(temporary.rglob("framework/bin/defects4j"))
        if len(candidates) != 1:
            raise CommandError(
                "The archive must contain exactly one Defects4J distribution with "
                "framework/bin/defects4j; found " + str(len(candidates))
            )
        extracted_root = candidates[0].parents[2]
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(extracted_root), str(destination))
        _repair_permissions(destination)
        return destination
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _repair_permissions(root: Path) -> None:
    candidates = [
        root / "init.sh",
        root / "framework" / "bin" / "defects4j",
        root / "project_repos" / "get_repos.sh",
    ]
    candidates.extend((root / "framework" / "bin" / "d4j").glob("d4j-*"))
    for path in candidates:
        if path.is_file():
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_distribution_root(value: Path) -> Path:
    value = value.expanduser().resolve()
    if value.is_file() and value.name == "defects4j":
        if value.parent.name != "bin" or value.parent.parent.name != "framework":
            raise CommandError(f"Unrecognized Defects4J executable location: {value}")
        return value.parents[2]
    if value.is_dir() and (value / "framework" / "bin" / "defects4j").is_file():
        return value
    raise CommandError(
        f"Defects4J root or executable was not found at {value}. "
        "Pass an initialized root, framework/bin/defects4j, or a .zip source archive."
    )


def _detect_version(root: Path, archive: Path | None = None) -> str | None:
    candidates = [root.name, archive.stem if archive else ""]
    for candidate in candidates:
        match = re.search(r"defects4j[-_]?([0-9]+(?:\.[0-9]+){1,2})", candidate, re.IGNORECASE)
        if match:
            return match.group(1)
    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Defects4J version\s+([0-9]+(?:\.[0-9]+){0,2})", text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _initialized_missing(root: Path) -> list[str]:
    checks = {
        "project repositories": root / "project_repos" / "README",
        "Major": root / "major" / "bin" / "ant",
        "test-generation libraries": root / "framework" / "lib" / "test_generation" / "generation",
        "Gradle distributions": root / "framework" / "lib" / "build_systems" / "gradle" / "dists",
        "Gradle dependencies": root / "framework" / "lib" / "build_systems" / "gradle" / "deps",
    }
    return [label for label, path in checks.items() if not path.exists()]


def is_initialized(root: Path) -> bool:
    return not _initialized_missing(root)


def _require_setup_tools() -> None:
    missing = [name for name in _REQUIRED_EXECUTABLES if shutil.which(name) is None]
    if missing:
        raise CommandError(
            "Defects4J setup requires missing command(s): "
            + ", ".join(missing)
            + ". Install the Defects4J 3.0.1 prerequisites before retrying."
        )


def _stream_command(
    command: list[str],
    *,
    cwd: Path,
    reporter: ConsoleReporter | None,
    log_file: Path,
    description: str,
    env: dict[str, str] | None = None,
) -> None:
    _log(reporter, LogLevel.INFO, description)
    _log(reporter, LogLevel.DEBUG, "Command: " + " ".join(command))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(command) + "\n")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=(os.environ.copy() if env is None else env),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            text = line.rstrip("\n")
            log.write(line)
            log.flush()
            if text:
                _log(reporter, LogLevel.INFO, f"[DEFECTS4J SETUP] {text}")
        return_code = process.wait()
    if return_code != 0:
        raise CommandError(
            f"{description} failed with exit code {return_code}. See setup log: {log_file}"
        )


def _required_perl_modules(root: Path) -> list[str]:
    cpanfile = root / "cpanfile"
    if not cpanfile.is_file():
        return []
    text = cpanfile.read_text(encoding="utf-8", errors="replace")
    return list(dict.fromkeys(re.findall(r"requires\s+['\"]([^'\"]+)['\"]", text)))


def _perl_dependencies_status(root: Path) -> tuple[bool, str]:
    modules = _required_perl_modules(root)
    if not modules:
        return True, "no cpanfile dependencies"
    executable = root / "framework" / "bin" / "defects4j"
    command = [shutil.which("perl") or "perl", *[f"-M{name}" for name in modules], "-e", "print qq(EFL_PERL_OK\n)"]
    completed = subprocess.run(
        command,
        cwd=root,
        env=defects4j_environment(executable),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode == 0:
        return True, "all required Perl modules load successfully"
    detail = [line.strip() for line in (completed.stderr or completed.stdout).splitlines() if line.strip()]
    if not detail:
        return False, "required Perl module validation failed"
    informative = next((line for line in detail if "Can't locate" in line), detail[0])
    return False, informative


def _validate_defects4j_cli(root: Path) -> None:
    executable = root / "framework" / "bin" / "defects4j"
    cmd = [str(executable), "pids"]
    if os.name == "nt" and not str(executable).lower().endswith((".exe", ".bat", ".cmd")):
        perl = shutil.which("perl") or r"C:\Program Files\Git\usr\bin\perl.exe"
        if os.path.isfile(perl):
            cmd = [perl, str(executable), "pids"]
    completed = subprocess.run(
        cmd,
        cwd=root,
        env=defects4j_environment(executable),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout)[-4000:]
        raise CommandError(
            "Defects4J initialization files exist, but its CLI is not usable. "
            f"Command failed: {executable} pids\n{tail}"
        )


def _setup_distribution(root: Path, setup_mode: str, reporter: ConsoleReporter | None) -> None:
    missing = _initialized_missing(root)
    if setup_mode not in {"auto", "refresh", "never"}:
        raise CommandError(f"Unsupported Defects4J setup mode: {setup_mode}")

    perl_ok, perl_detail = _perl_dependencies_status(root)
    if setup_mode == "never":
        if missing:
            raise CommandError(
                f"Defects4J is extracted but not initialized at {root}. Missing: {', '.join(missing)}. "
                "Re-run with --defects4j-setup auto."
            )
        if not perl_ok:
            raise CommandError(
                "Defects4J Perl dependencies are not usable: " + perl_detail + ". "
                "Re-run with --defects4j-setup auto."
            )
        _validate_defects4j_cli(root)
        return

    if not missing and perl_ok and setup_mode == "auto":
        _validate_defects4j_cli(root)
        _log(reporter, LogLevel.INFO, f"[CACHE HIT] initialized Defects4J framework: {root}")
        return

    _require_setup_tools()
    init_script = root / "init.sh"
    if not init_script.is_file():
        raise CommandError(f"Defects4J init.sh was not found: {init_script}")
    _repair_permissions(root)
    log_file = root / ".efl-defects4j-setup.log"
    cpan_marker = root / ".efl-cpan-deps.json"
    vendor_root = root / ".efl-perl5"

    reinstall_perl = setup_mode == "refresh" or not perl_ok
    if reinstall_perl:
        if not perl_ok:
            _log(reporter, LogLevel.WARNING, f"[CACHE INVALID] Defects4J Perl dependencies: {perl_detail}")
        if setup_mode == "refresh" and vendor_root.exists():
            shutil.rmtree(vendor_root)
        _stream_command(
            [
                shutil.which("cpanm") or "cpanm",
                "--local-lib-contained",
                str(vendor_root),
                "--installdeps",
                ".",
            ],
            cwd=root,
            reporter=reporter,
            log_file=log_file,
            description="Installing Defects4J Perl dependencies into the framework cache",
        )
        perl_ok, perl_detail = _perl_dependencies_status(root)
        if not perl_ok:
            cpan_marker.unlink(missing_ok=True)
            raise CommandError(
                "cpanm completed, but Defects4J Perl dependency validation failed: "
                f"{perl_detail}. See setup log: {log_file}"
            )
        cpan_marker.write_text(
            json.dumps(
                {
                    "complete": True,
                    "install_root": str(vendor_root),
                    "library_path": str(vendor_root / "lib" / "perl5"),
                    "modules": _required_perl_modules(root),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        _log(reporter, LogLevel.INFO, f"[CACHE HIT] Defects4J Perl dependencies: {root}")

    if missing or setup_mode == "refresh":
        _stream_command(
            [str(init_script)],
            cwd=root,
            reporter=reporter,
            log_file=log_file,
            description="Initializing Defects4J project repositories and external libraries",
            env=defects4j_environment(root / "framework" / "bin" / "defects4j"),
        )
    else:
        _log(reporter, LogLevel.INFO, f"[CACHE HIT] Defects4J repositories and external libraries: {root}")

    missing_after = _initialized_missing(root)
    if missing_after:
        raise CommandError(
            "Defects4J setup finished but the installation is incomplete. Missing: "
            + ", ".join(missing_after)
            + f". See {log_file}"
        )
    _validate_defects4j_cli(root)
    (root / ".efl-defects4j-ready.json").write_text(
        json.dumps(
            {
                "complete": True,
                "version": _detect_version(root),
                "perl_library": str(vendor_root / "lib" / "perl5"),
                "cli_validated": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prepare_defects4j(
    value: Path,
    *,
    cache_root: Path | None,
    setup_mode: str,
    reporter: ConsoleReporter | None,
) -> Defects4JFramework:
    source = value.expanduser().resolve()
    archive: Path | None = None
    digest: str | None = None

    if source.is_file() and source.suffix.lower() == ".zip":
        archive = source
        if cache_root is None:
            raise CommandError(
                "A Defects4J .zip input requires a cache directory. Pass --defects4j-cache PATH."
            )
        cache = cache_root.expanduser().resolve()
        cache.mkdir(parents=True, exist_ok=True)
        digest = _sha256(archive)
        destination = cache / f"{_safe_name(archive.stem)}-{digest[:12]}"
        marker = destination / ".efl-defects4j-archive.json"
        reusable = False
        if marker.is_file() and (destination / "framework" / "bin" / "defects4j").is_file():
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                reusable = payload.get("sha256") == digest
            except (OSError, ValueError, json.JSONDecodeError):
                reusable = False
        if reusable:
            _log(reporter, LogLevel.INFO, f"[CACHE HIT] extracted Defects4J archive: {destination}")
        else:
            _extract_zip(archive, destination, reporter)
            marker.write_text(
                json.dumps(
                    {
                        "archive": str(archive),
                        "sha256": digest,
                        "extracted_root": str(destination),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        root = destination
    else:
        root = _find_distribution_root(source)

    executable = root / "framework" / "bin" / "defects4j"
    if not executable.is_file():
        raise CommandError(f"Defects4J executable not found after preparation: {executable}")
    _repair_permissions(root)
    _setup_distribution(root, setup_mode, reporter)
    return Defects4JFramework(
        root=root,
        executable=executable,
        initialized=is_initialized(root),
        version=_detect_version(root, archive),
        archive_sha256=digest,
    )
