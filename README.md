# Defects4J Instrumenter & Dataset Generator

[![Version](https://img.shields.io/badge/version-1.3.5-blue.svg)](file:///D:/personal/defects4j_instrumenter/VERSION)
[![Changelog](https://img.shields.io/badge/changelog-available-green.svg)](file:///D:/personal/defects4j_instrumenter/CHANGELOG.md)

A standalone, automated instrumentation engine and dataset generator for the **Defects4J** Java benchmark suite.

This project instruments Java classes at the bytecode level, captures execution traces as sequences of predicate points (`P1, P2, ...`), identifies **Coincidental Correctness (CC)**, and produces standardized datasets identical to the Siemens benchmark format.

---

## 🚀 Key Features

1. **Bytecode Instrumentation (Java Agent)**:
   - Powered by `java.lang.instrument` and **ASM** bytecode manipulation.
   - Automatically injects probes (`TraceRuntime.record(predicateId)`) at deterministic line/statement locations without modifying original Java source files on disk.
2. **Automated Defect & Test Orchestration**:
   - Manages Defects4J checkouts (buggy `b` vs fixed `f` versions), compilation, and test execution.
   - Collects binary execution traces per test method and merges them into execution paths.
3. **Fault Mapping & Coincidental Correctness (CC) Detection**:
   - Computes AST/git unified diffs between buggy and fixed code (`source_changes.json`).
   - Maps mutated lines directly to basic-block/line predicate IDs (`source_map.csv`).
   - Tags passing tests that traverse faulty predicates as **Coincidentally Correct (`CC`)**.
4. **Unified Output Templates**:
   - Generates exact dataset templates matching the Siemens suite for seamless ML / SBFL ingestion.

---

## 📁 Repository Structure

```text
defects4j_instrumenter/
├── java-agent/                         # Core Java bytecode instrumentation agent
│   ├── src/main/java/org/efl/defects4j/
│   │   ├── agent/                      # Agent, Config, Transformer, PredicateMap, TraceRuntime
│   │   └── tools/                      # ClassScanner, TestEnumerator
│   ├── build.py                        # Automated agent compiler (produces JARs)
│   └── build.sh / build.ps1
├── defects4j_efl_instrumenter/         # Python orchestrator package
│   ├── agent.py                        # Agent build & JVM option injector
│   ├── cache_support.py                # Hash-based caching and fingerprinting
│   ├── cli.py                          # Low-level CLI commands
│   ├── commands.py                     # Defects4J process runners
│   ├── framework.py                    # Defects4J extraction & environment setup
│   ├── metadata.py                     # Source & test discovery
│   ├── models.py                       # Data classes (TestRun, BugRef, etc.)
│   ├── patch.py                        # Diff & mutated lines resolver
│   ├── progress.py                     # Console progress reporting
│   ├── runner.py                       # Suite runner & worker pool
│   └── trace.py                        # Trace binary decoder & dataset writer
├── scripts/                            # Helper scripts
│   ├── build_agent.ps1                 # Windows PowerShell agent build
│   ├── build_agent.sh                  # Linux/WSL bash agent build
│   ├── run_defects4j.sh                # Linux/WSL runner wrapper
│   └── test_all.sh                     # Unit test runner
├── tests/                              # Integration & unit tests
├── run_defects4j.py                    # High-level entry point runner
└── pyproject.toml                      # Python package definition
```

---

## 📊 Dataset Output Format (`efl-dataset-v2`)

For each bug version (e.g. `Lang-1`, `Math-5`), the instrumenter writes a single compact, self-describing directory under `work/results/<project>/v<id>/<test_set>/` (see `../DATASET_FORMAT_README.md` and `work/results/DATASET_README.md` for full field-level details and source-mapping instructions):

### 1. `traces.tsv.gz` (Canonical Lossless Compressed Traces)
Gzip-compressed UTF-8 TSV with header:
```tsv
test_id	status	cc	path
T1	T	0	1 2 3 4 4 3 5
T2	T	1	1 2 4 5
T3	F	0	1 2 4 6
```
- `test_id`: Short identifier (`T1..TN`) mapped to full JUnit methods in `tests.tsv`.
- `status`: Strict oracle verdict (`T` = Pass, `F` = Fail).
- `cc`: Ground-truth Coincidental Correctness (`1` if `status=T` and execution visited a fault predicate, else `0`).
- `path`: Space-separated integer predicate IDs (`1 2 3 ...`) matching `id` in `source_map.csv`.

### 2. `tests.tsv`
Complete inventory of all discovered tests (`T1..TN` included, `X1..XM` excluded) mapping `test_id` to the exact JUnit method (`pkg.Class#method`), `status`, `cc`, `included`, `trace_len`, `duration_sec`, `return_code`, `timed_out`, and `reason`.

### 3. `summary.json`, `source_map.csv`, `source_changes.json`, `metadata.json`, `cache_manifest.json`
- `summary.json`: Compact aggregate counts, instrumentation metadata (`bytecode_line`, `java_asm_agent`, `scope`), and `fault_predicate_ids` without duplicating trace paths.
- `source_map.csv`: Maps each integer `id` (`P<id>`) to `file`, `line`, `function`, `class`, `method`, `descriptor`.
- `source_changes.json`: Diff lines between buggy (`v<id>b`) and fixed (`v<id>f`) sources.
- Raw `tests/*/trace.bin` and `checkouts/` are cleaned automatically once `traces.tsv.gz` is verified (pass `--keep-raw-traces` or `--keep-checkouts` to retain them).

---

## ⚙️ Prerequisites

1. **Python 3.10+**
2. **Java 11 (JDK 11)**:
   - Defects4J 3.0.1 requires JDK 11.
   - Set `JAVA_HOME` or provide `--java-home`.
3. **Defects4J 3.0.1**:
   - Supported natively on Linux and Windows via **WSL2** (due to Defects4J's Perl/Bash dependencies).
   - Can be passed as a `.zip` archive or an existing extracted folder.

---

## 🛠️ Usage (Linux)

### 1. Install Prerequisites (Ubuntu / Debian)
```bash
sudo apt update && sudo apt install -y openjdk-11-jdk git subversion perl cpanminus curl unzip
```

### 2. Run Instrumentation & Generate Datasets
The `./run.sh` script automatically detects `defects4j-3.0.1.zip` in the root:

```bash
# Run a single bug version:
./run.sh --projects Lang --bugs 1

# Run multiple bugs with 4 parallel worker threads:
./run.sh --projects Math --bugs 1,2,5 --jobs 4

# Run all bugs for a specific project:
./run.sh --projects Chart --test-selection relevant --jobs 4

# Run the standard benchmark profile (scd4fl-2024: 395 bugs across 6 core projects):
./run.sh --profile scd4fl-2024 --jobs 0

# Run ABSOLUTE ALL 17 projects and 835+ bugs in Defects4J:
./run.sh --jobs 0
```

### 3. Benchmark Scope & Test Selection Options

* **Benchmark Scope**:
  - **`--profile scd4fl-2024`**: Standard paper evaluation suite covering 6 classical projects (total **395 bugs**):
    - `Chart` (26 bugs), `Closure` (133 bugs), `Lang` (65 bugs), `Math` (106 bugs), `Mockito` (38 bugs), `Time` (27 bugs).
  - **Omit `--profile`**: Executes **ALL 17 projects** and **835+ bugs** present in Defects4J 3.0.1 (including `Cli`, `Codec`, `Collections`, `Compress`, `Csv`, `Gson`, `JacksonCore`, `JacksonDatabind`, `JacksonXml`, `Jsoup`, `JxPath`).

* **Test Selection (`--test-selection <mode>`)**:
  - **`relevant`** (Default & Recommended): Runs tests executing modified/buggy classes (tens to hundreds of tests per bug). Accurately balances execution time while collecting PASS, CC, and FAIL paths.
  - **`all`**: Runs the entire test suite of the project (can be 10,000+ tests per bug).
  - **`trigger`**: Runs only test cases that fail/trigger the bug (1-3 tests per bug).

### 4. Rebuild Java Agent (Optional)
The agent JARs are pre-built in `java-agent/build/`. To rebuild manually:
```bash
./scripts/build_agent.sh
```

---

## 🧪 Testing

Run test suite:
```bash
python -m unittest discover -s tests -v
```

---

## 📌 Versioning & Changelog

The project version is centrally defined in [VERSION](file:///D:/personal/defects4j_instrumenter/VERSION) and dynamically referenced by:
- `pyproject.toml` (PEP 621 dynamic metadata)
- `defects4j_efl_instrumenter` package (`__version__`)
- `java-agent/build.py` (writes `Implementation-Version` to `MANIFEST.MF`)
- `run_defects4j.py` and CLI `--version`

For a complete history of changes, see [CHANGELOG.md](file:///D:/personal/defects4j_instrumenter/CHANGELOG.md).

