from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from defects4j_efl_instrumenter.commands import CommandError, configure_java_home, d4j
from defects4j_efl_instrumenter.framework import (
    _setup_distribution,
    download_defects4j,
    prepare_defects4j,
)


def _zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def _write_distribution_zip(path: Path, *, initialized: bool) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        root = "defects4j-3.0.1/"
        archive.writestr(_zip_info(root + "framework/bin/defects4j", stat.S_IFREG | 0o755), "#!/bin/sh\nexit 0\n")
        archive.writestr(_zip_info(root + "init.sh", stat.S_IFREG | 0o755), "#!/bin/sh\nexit 0\n")
        archive.writestr(_zip_info(root + "README.md", stat.S_IFREG | 0o644), "Defects4J version 3.0.1\n")
        archive.writestr(_zip_info(root + "links/target.txt", stat.S_IFREG | 0o644), "target\n")
        archive.writestr(_zip_info(root + "links/link.txt", stat.S_IFLNK | 0o777), "target.txt")
        if initialized:
            archive.writestr(_zip_info(root + "project_repos/README", stat.S_IFREG | 0o644), "Defects4J version 3\n")
            archive.writestr(_zip_info(root + "major/bin/ant", stat.S_IFREG | 0o755), "#!/bin/sh\n")
            archive.writestr(_zip_info(root + "framework/lib/test_generation/generation/.keep", stat.S_IFREG | 0o644), "")
            archive.writestr(_zip_info(root + "framework/lib/build_systems/gradle/dists/.keep", stat.S_IFREG | 0o644), "")
            archive.writestr(_zip_info(root + "framework/lib/build_systems/gradle/deps/.keep", stat.S_IFREG | 0o644), "")


class FrameworkZipTests(unittest.TestCase):
    def test_zip_input_extracts_preserves_links_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "defects4j-3.0.1.zip"
            cache = root / "cache"
            _write_distribution_zip(archive, initialized=True)

            first = prepare_defects4j(archive, cache_root=cache, setup_mode="never", reporter=None)
            self.assertTrue(first.initialized)
            self.assertEqual(first.version, "3.0.1")
            self.assertTrue(first.executable.is_file())
            self.assertTrue(os.access(first.executable, os.X_OK))
            self.assertTrue((first.root / "links/link.txt").is_symlink())
            self.assertEqual((first.root / "links/link.txt").read_text(), "target\n")

            marker = first.root / ".efl-defects4j-archive.json"
            payload = json.loads(marker.read_text())
            self.assertEqual(payload["sha256"], first.archive_sha256)
            sentinel = first.root / "sentinel"
            sentinel.write_text("keep")

            second = prepare_defects4j(archive, cache_root=cache, setup_mode="never", reporter=None)
            self.assertEqual(second.root, first.root)
            self.assertEqual(sentinel.read_text(), "keep")

    def test_uninitialized_zip_reports_setup_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "defects4j-3.0.1.zip"
            _write_distribution_zip(archive, initialized=False)
            with self.assertRaisesRegex(CommandError, "not initialized"):
                prepare_defects4j(archive, cache_root=root / "cache", setup_mode="never", reporter=None)

    def test_zip_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape", "bad")
            with self.assertRaisesRegex(CommandError, "Unsafe path"):
                prepare_defects4j(archive, cache_root=root / "cache", setup_mode="never", reporter=None)

    def test_configure_java_home_uses_supplied_java_11(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "jdk-11"
            bin_dir = home / "bin"
            bin_dir.mkdir(parents=True)
            for name, body in {
                "java": '#!/bin/sh\necho \'openjdk version "11.0.25"\' 1>&2\n',
                "javac": "#!/bin/sh\nexit 0\n",
            }.items():
                path = bin_dir / name
                path.write_text(body)
                path.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=False):
                os.environ.pop("JAVA_HOME", None)
                configure_java_home(home)
                self.assertEqual(os.environ["JAVA_HOME"], str(home.resolve()))
                self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], str(bin_dir.resolve()))

    def test_d4j_automatically_uses_cache_local_perl_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "defects4j-3.0.1"
            executable = root / "framework" / "bin" / "defects4j"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\nprintf '%s' \"$PERL5LIB\"\n", encoding="utf-8")
            executable.chmod(0o755)
            library = root / ".efl-perl5" / "lib" / "perl5"
            library.mkdir(parents=True)

            completed = d4j(executable, ["pids"])
            self.assertEqual(completed.stdout, str(library))

    def test_auto_setup_repairs_stale_perl_marker_in_framework_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "defects4j-3.0.1"
            executable = root / "framework" / "bin" / "defects4j"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            (root / "init.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (root / "init.sh").chmod(0o755)
            (root / "cpanfile").write_text("requires 'EFL::FakePerlDependency';\n", encoding="utf-8")
            (root / ".efl-cpan-deps.json").write_text('{"complete": true}\n', encoding="utf-8")

            for path in [
                root / "project_repos" / "README",
                root / "major" / "bin" / "ant",
                root / "framework" / "lib" / "test_generation" / "generation" / ".keep",
                root / "framework" / "lib" / "build_systems" / "gradle" / "dists" / ".keep",
                root / "framework" / "lib" / "build_systems" / "gradle" / "deps" / ".keep",
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            calls: list[list[str]] = []

            def fake_stream(command: list[str], **_: object) -> None:
                calls.append(command)
                module = root / ".efl-perl5" / "lib" / "perl5" / "EFL" / "FakePerlDependency.pm"
                module.parent.mkdir(parents=True, exist_ok=True)
                module.write_text("package EFL::FakePerlDependency; 1;\n", encoding="utf-8")

            with mock.patch(
                "defects4j_efl_instrumenter.framework._require_setup_tools"
            ), mock.patch(
                "defects4j_efl_instrumenter.framework._stream_command", side_effect=fake_stream
            ):
                _setup_distribution(root, "auto", reporter=None)

            self.assertEqual(len(calls), 1)
            self.assertIn("--local-lib-contained", calls[0])
            marker = json.loads((root / ".efl-cpan-deps.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["install_root"], str(root / ".efl-perl5"))
            self.assertTrue((root / ".efl-defects4j-ready.json").is_file())

    def test_download_defects4j_skips_when_valid_zip_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "defects4j-3.0.1.zip"
            _write_distribution_zip(destination, initialized=True)
            with mock.patch("urllib.request.urlopen") as mock_url:
                result = download_defects4j(destination)
                mock_url.assert_not_called()
                self.assertEqual(result, destination)

    def test_download_defects4j_downloads_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "defects4j-3.0.1.zip"
            dummy_zip = Path(directory) / "dummy.zip"
            _write_distribution_zip(dummy_zip, initialized=True)
            dummy_bytes = dummy_zip.read_bytes()

            class DummyResponse:
                def __init__(self, data: bytes):
                    self.data = data
                    self.headers = {"Content-Length": str(len(data))}
                    self.offset = 0

                def read(self, size: int = -1) -> bytes:
                    if self.offset >= len(self.data):
                        return b""
                    chunk = self.data[self.offset : self.offset + size]
                    self.offset += len(chunk)
                    return chunk

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            with mock.patch("urllib.request.urlopen", return_value=DummyResponse(dummy_bytes)):
                result = download_defects4j(destination)
                self.assertTrue(result.is_file())
                self.assertEqual(result.read_bytes(), dummy_bytes)


if __name__ == "__main__":
    unittest.main()
