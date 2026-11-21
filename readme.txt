########################################################################
# Defects4J Java Bytecode Instrumenter & Benchmark Suite Runner (Linux)
########################################################################

This project is a standalone, automated instrumentation engine and dataset
generator for the Defects4J (Java) benchmark suite.

It performs ASM-based bytecode instrumentation at JVM runtime, traces
basic-block and line predicate sequences (P-points), detects Coincidental
Correctness (CC), and generates standard datasets identical to the Siemens
benchmark suite.

########################################################################
## 1. System Requirements & Setup (Debian / Ubuntu / Linux):
########################################################################

Defects4J requires JDK 11 and a few Unix tools (git, svn, perl, cpanm).
Install them via apt:

  sudo apt update
  sudo apt install -y openjdk-11-jdk git subversion perl cpanminus curl unzip

Verify Java 11:
  java -version
  javac -version

########################################################################
## 2. Execution Commands:
########################################################################

The root script './run.sh' automatically locates 'defects4j-3.0.1.zip'
and configures the environment:

  # 1. Run a single bug version (e.g. Lang bug 1):
  ./run.sh --projects Lang --bugs 1

  # 2. Run multiple bugs with 4 parallel worker threads:
  ./run.sh --projects Math --bugs 1,2,5 --jobs 4

  # 3. Run all bugs for a specific project:
  ./run.sh --projects Chart --test-selection relevant --jobs 4

  # 4. Standard Paper Benchmark Profile (scd4fl-2024: 395 bugs across 6 core projects):
  ./run.sh --profile scd4fl-2024 --jobs 0

  # 5. ABSOLUTE MAXIMUM - All 17 projects & all 835+ bugs in Defects4J 3.0.1:
  ./run.sh --jobs 0

  # Or invoke via Python directly:
  python3 run_defects4j.py --projects Lang --bugs 1

########################################################################
## 3. Scope of Benchmark Profiles & Test Selection:
########################################################################

A) Benchmark Scope:
  - Standard Paper Profile (--profile scd4fl-2024):
    Covers the 6 classical, widely-studied projects in Fault Localization
    literature (total 395 bugs):
      * Chart   : 26 bugs (v1 - v26)
      * Closure : 133 bugs (v1 - v133)
      * Lang    : 65 bugs (v1 - v65)
      * Math    : 106 bugs (v1 - v106)
      * Mockito : 38 bugs (v1 - v38)
      * Time    : 27 bugs (v1 - v27)

  - Full Benchmark Run (omit --profile):
    Runs ALL 17 projects in Defects4J 3.0.1 (total 835+ bugs), including
    Cli, Codec, Collections, Compress, Csv, Gson, JacksonCore,
    JacksonDatabind, JacksonXml, Jsoup, JxPath, Lang, Math, Mockito, Time.
    Command: ./run.sh --jobs 0

B) Test Selection (--test-selection <mode>):
  - 'relevant' (Default & Recommended):
    Runs all tests related to modified/buggy classes (tens to hundreds of
    tests per bug). This is the standard in literature, capturing PASS, CC,
    and FAIL tests without excessive overhead.
  - 'all' (Absolute Maximum):
    Executes the entire test suite of the project (can be 10,000+ tests per
    bug; very time-consuming).
  - 'trigger' (Minimal Debug):
    Executes ONLY the test cases that fail/trigger the bug (1-3 tests per bug).

########################################################################
## 4. Java Agent Build Commands:
########################################################################

The Java Bytecode Agent (defects4j-efl-agent.jar & defects4j-efl-runtime.jar)
is pre-built in 'java-agent/build/'. If you ever need to recompile it:

  bash scripts/build_agent.sh

########################################################################
## 5. Output Datasets & Directory Structure:
########################################################################

All output datasets are automatically generated and mirrored in:
  output/datasets/<project>/

For each instrumented bug version (e.g. Lang v1), the following files are produced:

  output/datasets/Lang/
  ├── v1_dataset.txt               # Strict binary FL dataset (P-traces + T/F)
  ├── v1_tagged.txt                # 3-state CC dataset (P-traces + T/CC/F)
  ├── v1_detailed.json             # Full structural & test-by-test metadata
  ├── cmp.v0.v1.Lang.csv           # EFL Stage 2 compatible 3-field CSV
  ├── source_map.csv               # Predicate-to-source-line mapping
  └── source_changes.json          # Ground-truth mutated line diffs

Detailed checkouts and per-test logs are stored in:
  output/results/<project>/v<bug_id>/relevant/

########################################################################
## 6. Differences Between _dataset.txt and _tagged.txt:
########################################################################

For each tested bug version (e.g. Lang v1, Math v5), two dataset text files
are generated. In both files, lines 1 through N are 100% IDENTICAL:
each line represents the execution trace (the sequence of P-points visited)
for that test case.

The ONLY difference is in the FINAL LINE (the test verdict vector):

1) <version>_dataset.txt (Binary Pass / Fail):
   The final line contains only 'T' (Pass) and 'F' (Fail).
     - 'F' : Fail (test failed or exception thrown).
     - 'T' : Pass (test passed, regardless of whether the fault site
             was visited or not).

   Example format:
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P6,P7,P10,P12
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P10,P12
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P9,P10,P12
     T,T,T,F,T,F,F,T,T,T

   Use case: Ideal for standard machine learning classifiers, neural FL,
   and traditional Spectrum-Based Fault Localization (SBFL) algorithms
   (such as Ochiai, Tarantula, DStar) that require a binary Pass/Fail label.

2) <version>_tagged.txt (3-State with Coincidental Correctness Tag):
   The final line classifies tests into 3 categories: 'T', 'CC', and 'F'.
     - 'F'  : Fail (the fault was executed and caused test failure).
     - 'CC' : Coincidentally Correct (the fault predicate was EXECUTED
              in the trace, but the test PASSED because the fault was masked
              and did not propagate to an assertion failure).
     - 'T'  : Pure Pass (test passed and the fault predicate was NOT executed).

   Example format:
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P6,P7,P10,P12
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P10,P12
     P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P9,P10,P12
     T,T,CC,F,T,CC,F,T,T,T

   Use case: Essential for advanced Fault Localization techniques (such as
   EFL - Entropy Fault Localization) that identify and isolate coincidental
   correctness to prevent ranking distortion.

########################################################################
## 7. Running Automated Self-Tests:
########################################################################

To verify the test suite:

  bash scripts/test_all.sh
