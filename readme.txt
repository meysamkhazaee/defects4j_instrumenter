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

Defects4J requires JDK 11 and Unix toolchain packages.
Install them via apt:

  sudo apt update
  sudo apt install -y openjdk-11-jdk git subversion perl cpanminus curl unzip

Verify Java 11:
  java -version
  javac -version

########################################################################
## 2. Defects4J 3.0.1 Projects & Sub-Suites Catalog (17 Projects, 838 Bugs):
########################################################################

A) The Classical 6 Research Projects (395 bugs - Standard in FL Literature):
   - Chart          : 26 bugs  [v1 - v26]   | JFreeChart 2D chart library      (Fast)
   - Time           : 27 bugs  [v1 - v27]   | Joda-Time date/time library      (Fast)
   - Mockito        : 38 bugs  [v1 - v38]   | Mockito mocking framework        (Medium)
   - Lang           : 65 bugs  [v1 - v65]   | Apache Commons Lang utilities    (Fast)
   - Math           : 106 bugs [v1 - v106]  | Apache Commons Math library      (Medium)
   - Closure        : 133 bugs [v1 - v133]  | Google Closure JS compiler       (Heavy)
   Total: 395 bugs (covered by '--profile scd4fl-2024')

B) The 11 Extended Projects (443 bugs - Added in Defects4J v2/v3):
   - Csv            : 16 bugs  [v1 - v16]   | Apache Commons CSV parser        (Ultra Fast)
   - Codec          : 18 bugs  [v1 - v18]   | Apache Commons Codec (Base64)    (Ultra Fast)
   - Gson           : 18 bugs  [v1 - v18]   | Google Gson JSON library         (Fast)
   - JxPath         : 22 bugs  [v1 - v22]   | Apache Commons JXPath            (Fast)
   - JacksonCore    : 26 bugs  [v1 - v26]   | Jackson JSON streaming parser    (Fast)
   - JacksonXml     : 6 bugs   [v1 - v6]    | Jackson XML dataformat           (Ultra Fast)
   - Collections    : 28 bugs  [v1 - v28]   | Apache Commons Collections       (Medium)
   - Cli            : 40 bugs  [v1 - v40]   | Apache Commons CLI parser        (Medium)
   - Compress       : 47 bugs  [v1 - v47]   | Apache Commons Compress          (Medium)
   - Jsoup          : 93 bugs  [v1 - v93]   | Jsoup Java HTML parser           (Medium)
   - JacksonDatabind: 112 bugs [v1 - v112]  | Jackson general data-binding     (Heavy)

Grand Total across all 17 projects: 838 real bugs.

########################################################################
## 3. High-Performance Execution Commands (Recommended Tiers):
########################################################################

To avoid massive execution times, ALWAYS use '--test-selection relevant'
and run projects from fastest to heaviest:

--- TIER 1: Ultra-Fast Quick Start (Takes ~15-30 minutes total) ---
Run lightweight projects to get instant datasets:
  ./run.sh --projects Csv,Codec,Gson,Chart,Time --test-selection relevant --jobs 8

--- TIER 2: Core Academic Libraries (Takes ~1-2 hours) ---
Run the main Apache Commons and Math projects:
  ./run.sh --projects Lang,Math --test-selection relevant --jobs 8

--- TIER 3: Remaining Medium Projects (Takes ~1-2 hours) ---
  ./run.sh --projects Cli,Collections,Compress,JacksonCore,JacksonXml,JxPath --test-selection relevant --jobs 8

--- TIER 4: Heavy Projects (Run individually overnight) ---
  ./run.sh --projects Mockito --test-selection relevant --jobs 8
  ./run.sh --projects Jsoup --test-selection relevant --jobs 8
  ./run.sh --projects JacksonDatabind --test-selection relevant --jobs 8
  ./run.sh --projects Closure --test-selection relevant --jobs 8

########################################################################
## 4. Benchmark Profile & Full Suite Commands:
########################################################################

  # 1. Run a single bug version (e.g. Lang bug 1):
  ./run.sh --projects Lang --bugs 1

  # 2. Run multiple specific bugs (e.g. Math bugs 1, 2, and 5):
  ./run.sh --projects Math --bugs 1,2,5 --jobs 4

  # 3. Standard Paper Benchmark Profile (scd4fl-2024: 395 bugs across 6 core projects):
  ./run.sh --profile scd4fl-2024 --test-selection relevant --jobs 8 --timeout 60

  # 4. ABSOLUTE MAXIMUM - All 17 projects & all 838 bugs in Defects4J 3.0.1:
  ./run.sh --test-selection relevant --jobs 8 --timeout 60

  # 5. Direct Python invocation:
  python3 run_defects4j.py --projects Lang --bugs 1

########################################################################
## 5. Performance Optimization Flags Explained:
########################################################################

1) --test-selection <mode>:
   - 'relevant' (CRITICAL - 50x-100x FASTER):
     Runs only tests targeting modified classes (tens to hundreds of tests
     per bug). Standard in all literature. DO NOT use 'all' for full suite
     runs as running 10,000+ tests per bug will take weeks.
   - 'trigger':
     Runs ONLY tests that fail/trigger the bug (1-3 tests per bug, instant).
   - 'all':
     Runs every single unit test in the entire repository (extremely slow).

2) --test-limit <N> (Optional Cap):
   Caps the maximum number of tests per bug (e.g. '--test-limit 80').
   Failing/triggering tests are ALWAYS placed first and guaranteed to execute.

3) --instrument-scope modified:
   Instruments only classes mutated by the bug fix, drastically reducing
   trace sizes and disk I/O.

4) --jobs <N>:
   Concurrent worker processes. Set explicitly to match CPU cores (e.g. -j 8
   or -j 16). Pass '--jobs 0' for automatic hardware-based calculation.

5) --timeout <seconds>:
   Default is 300s. Set '--timeout 60' so hanging tests do not block workers.

6) --cache reuse:
   Default is 'reuse'. If interrupted, re-running skips completed bugs instantly.

########################################################################
## 6. Java Agent Build Commands:
########################################################################

The Java Bytecode Agent (defects4j-efl-agent.jar & defects4j-efl-runtime.jar)
is pre-built in 'java-agent/build/'. If you ever need to recompile it:

  bash scripts/build_agent.sh

########################################################################
## 7. Output Datasets & Directory Structure:
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
## 8. Differences Between _dataset.txt and _tagged.txt:
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
## 9. Running Automated Self-Tests:
########################################################################

To verify the test suite:

  bash scripts/test_all.sh
