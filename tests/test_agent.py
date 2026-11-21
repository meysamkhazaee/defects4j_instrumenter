from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from defects4j_efl_instrumenter.agent import ensure_agent, java_command
from defects4j_efl_instrumenter.progress import ConsoleReporter, LogLevel


@unittest.skipUnless(shutil.which("java") and shutil.which("javac"), "Java toolchain required")
class AgentIntegrationTests(unittest.TestCase):
    def test_agent_records_ordered_source_lines(self) -> None:
        reporter = ConsoleReporter(level=LogLevel.ERROR, progress_enabled=False)
        agent = ensure_agent(asm_jar=None, reporter=reporter, rebuild=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "demo"
            classes = root / "classes"
            traces = root / "traces"
            source.mkdir(parents=True)
            classes.mkdir()
            traces.mkdir()
            java_file = source / "App.java"
            java_file.write_text(
                "package demo;\n"
                "public class App {\n"
                "  static int f(int x) {\n"
                "    int y = x + 1;\n"
                "    return y * 2;\n"
                "  }\n"
                "  public static void main(String[] a) { System.out.println(f(2)); }\n"
                "}\n",
                encoding="utf-8",
            )
            subprocess.run(["javac", "-g", "-d", str(classes), str(java_file)], check=True)
            bins = root / "bins.txt"
            filt = root / "filter.txt"
            bins.write_text(str(classes) + "\n", encoding="utf-8")
            filt.write_text("demo.App\n", encoding="utf-8")
            mapping = root / "mapping.tsv"
            source_map = root / "source_map.csv"
            subprocess.run(
                [*java_command(agent), "org.efl.defects4j.tools.ClassScanner", str(bins), str(filt), "src", str(mapping), str(source_map)],
                check=True,
            )
            properties = root / "agent.properties"
            properties.write_text(
                f"mapping={mapping.as_posix()}\noutput_dir={traces.as_posix()}\ndebug=false\n", encoding="utf-8"
            )
            subprocess.run(
                ["java", *agent.java_options, f"-javaagent:{agent.jar}={properties}", "-cp", str(classes), "demo.App"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            trace_file = next(traces.glob("*.bin"))
            values = [value[0] for value in struct.iter_unpack(">i", trace_file.read_bytes())]
            self.assertGreaterEqual(len(values), 3)
            self.assertEqual(values, list(dict.fromkeys(values)))


if __name__ == "__main__":
    unittest.main()
