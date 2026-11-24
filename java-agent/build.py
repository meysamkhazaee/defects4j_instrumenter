#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


def tool(name: str, java_home: Path | None) -> str:
    candidates = []
    if java_home:
        candidates.append(java_home / "bin" / (name + ".exe" if os.name == "nt" else name))
        candidates.append(java_home / "bin" / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"error: required Java tool not found: {name}")
    return found


def java_major(java: str) -> int | None:
    cp = subprocess.run([java, "-version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    m = re.search(r'version "(?:1\.)?([0-9]+)', cp.stdout)
    return int(m.group(1)) if m else None


def load_version() -> str:
    """Read version dynamically from project VERSION file."""
    candidates = [
        Path(__file__).resolve().parent.parent / "VERSION",
        Path(__file__).resolve().parent / "VERSION",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    return "1.3.5"



def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Defects4J EFL Java agent")
    parser.add_argument("--asm-jar", type=Path)
    parser.add_argument("--java-home", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    build = root / "build"
    source = root / "src" / "main" / "java"
    if build.exists():
        shutil.rmtree(build)
    (build / "classes").mkdir(parents=True)
    (build / "generated").mkdir(parents=True)

    java_home = args.java_home.expanduser().resolve() if args.java_home else None
    java = tool("java", java_home)
    javac = tool("javac", java_home)
    jar = tool("jar", java_home)

    mode = "jdk-internal"
    compile_source = source
    javac_args: list[str] = []

    if args.asm_jar:
        asm_jar = args.asm_jar.expanduser().resolve()
        if not asm_jar.is_file():
            raise SystemExit(f"error: ASM jar not found: {asm_jar}")
        mode = "external-asm"
        javac_args = ["-cp", str(asm_jar)]
        help_text = subprocess.run([javac, "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False).stdout
        javac_args += ["--release", "8"] if "--release" in help_text else ["-source", "8", "-target", "8"]
    else:
        major = java_major(java)
        if major is None or major < 11:
            raise SystemExit(
                "error: no external ASM jar was provided and the JDK-internal fallback requires Java 11+.\n"
                "For Defects4J 3.0.1 use JDK 11; for Java 8 use --asm-jar /path/to/asm-9.x.jar."
            )
        generated = build / "generated"
        shutil.copytree(source, generated, dirs_exist_ok=True)
        for path in generated.rglob("*.java"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("org.objectweb.asm", "jdk.internal.org.objectweb.asm"), encoding="utf-8")
        compile_source = generated
        javac_args = [
            "--add-exports", "java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED",
            "-source", "11", "-target", "11",
        ]

    sources = sorted(str(path) for path in compile_source.rglob("*.java"))
    if not sources:
        raise SystemExit(f"error: no Java sources found under {compile_source}")
    subprocess.run([javac, *javac_args, "-d", str(build / "classes"), *sources], check=True)

    class_dir = build / "classes"
    if mode == "external-asm":
        assert args.asm_jar is not None
        fat = build / "fat"
        shutil.copytree(build / "classes", fat, dirs_exist_ok=True)
        subprocess.run([jar, "xf", str(args.asm_jar.expanduser().resolve())], cwd=fat, check=True)
        meta = fat / "META-INF"
        if meta.is_dir():
            for pattern in ("*.SF", "*.RSA", "*.DSA"):
                for path in meta.glob(pattern):
                    path.unlink(missing_ok=True)
        class_dir = fat

    manifest = build / "MANIFEST.MF"
    manifest.write_text(
        "Manifest-Version: 1.0\n"
        "Premain-Class: org.efl.defects4j.agent.Agent\n"
        "Can-Redefine-Classes: false\n"
        "Can-Retransform-Classes: false\n"
        "Implementation-Title: EFL Defects4J Ordered Trace Agent\n"
        f"Implementation-Version: {load_version()}\n",
        encoding="utf-8",
    )
    agent_jar = build / "defects4j-efl-agent.jar"
    subprocess.run([jar, "cfm", str(agent_jar), str(manifest), "-C", str(class_dir), "."], check=True)

    runtime_jar = build / "defects4j-efl-runtime.jar"
    classes = build / "classes"
    subprocess.run([
        jar, "cf", str(runtime_jar),
        "-C", str(classes), "org/efl/defects4j/agent/TraceRuntime.class",
        "-C", str(classes), "org/efl/defects4j/agent/TraceRuntime$1.class",
    ], check=True)

    (build / "build-mode.txt").write_text(mode + "\n", encoding="utf-8")
    version_text = subprocess.run([java, "-version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False).stdout.splitlines()
    (build / "build-java-version.txt").write_text((version_text[0] if version_text else "unknown") + "\n", encoding="utf-8")
    print(f"Built {agent_jar} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
