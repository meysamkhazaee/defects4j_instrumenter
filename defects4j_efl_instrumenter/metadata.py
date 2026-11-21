from __future__ import annotations

from pathlib import Path

from .commands import export_property, split_lines, split_paths
from .models import VersionMetadata


def collect_metadata(executable: Path, project: str, bug_id: int, buggy: Path, fixed: Path) -> VersionMetadata:
    return VersionMetadata(
        project=project,
        bug_id=bug_id,
        buggy_root=buggy,
        fixed_root=fixed,
        source_dirs=split_paths(export_property(executable, buggy, "dir.src.classes"), buggy),
        class_dirs=split_paths(export_property(executable, buggy, "dir.bin.classes"), buggy),
        test_source_dirs=split_paths(export_property(executable, buggy, "dir.src.tests"), buggy),
        test_class_dirs=split_paths(export_property(executable, buggy, "dir.bin.tests"), buggy),
        classes_modified=split_lines(export_property(executable, buggy, "classes.modified")),
        classes_relevant=split_lines(export_property(executable, buggy, "classes.relevant")),
        tests_all_classes=split_lines(export_property(executable, buggy, "tests.all")),
        tests_relevant_classes=split_lines(export_property(executable, buggy, "tests.relevant")),
        tests_trigger_methods=split_lines(export_property(executable, buggy, "tests.trigger")),
        cp_compile=export_property(executable, buggy, "cp.compile"),
        cp_test=export_property(executable, buggy, "cp.test"),
    )
