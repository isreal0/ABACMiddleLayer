# ABAC Middle Layer — Cross-Engine Benchmark

This directory is the shared, engine-neutral research harness for evaluating the
ABAC Middle Layer (this repository's `abacml/` + `postgres/`) against three
independent authorization baselines, using one canonical set of authorization
scenarios and expected decisions.

## Systems under test

| Server | Public IP | Purpose | Native technology |
|---|---|---|---|
| DevInstance | 130.216.217.124 | ABAC Middle Layer under evaluation (this repo) | C, PostgreSQL, JNI -> Balana XACML PDP |
| DevInstance2 | 130.216.216.210 | SunXACML baseline | XACML 2.0, Java, legacy PDP |
| DevInstance3 | 130.216.217.221 | AuthzForce Core baseline | XACML 3.0, Java 17+, modern PDP |
| DevInstance4 | 130.216.216.147 | Casbin-CPP baseline | C++, embedded authorization, PERM model |

All four VMs run Ubuntu 22.04 LTS, Nectar `m3.large` (8 vCPU / 16 GB RAM / 30 GB disk).

## Reproduction entry point

Each VM keeps a local, identical checkout of this `benchmark/` subtree under
`/opt/abac-research/harness` (sparse checkout — the full `abacml`/`postgres`
tree is only present on DevInstance, where `/opt/abac-research/repo` is a
symlink to `~/project`, this repository's working copy).

```
# On any VM, after the canonical corpus exists (Step 4):
scripts/capture-environment.sh          # record hardware/software versions
scripts/run-correctness.sh <engine>     # correctness gate (Step 5A)
scripts/run-benchmark.sh <engine>       # controlled benchmark (Step 5B)
```

`<engine>` is one of: `middle-layer`, `sunxacml`, `authzforce`, `casbin-cpp`.

## Status

- **Step 0 (infra verification):** done — see `control/inventory.csv` on the
  coordinating machine.
- **Step 1 (workspace + this harness scaffold):** done — shared
  `/opt/abac-research` layout, common utilities, and this `benchmark/`
  subtree on all four VMs, pinned to the same commit.
- **Step 2 (Middle Layer implementation review/build):** in progress.
  Confirmed PDP = WSO2 Balana 1.1.12; added `ABACML.Evaluate_ABAC_Decision`
  with the full canonical UOA Canvas LMS attribute model and real
  Permit/Deny/NotApplicable/Indeterminate decisions, verified by a 4-case
  JUnit test, without touching the live Postgres/JNI path
  (`Check_ABAC_Permission`) or its policy directory. See
  `docs/architecture.md` and `docs/semantic-mapping.md`.
- **Step 3 (baseline installs):** done. SunXACML `2.0-M1` JAR pinned on
  DevInstance2. AuthzForce Core built clean (all 5 modules) on DevInstance3,
  commit `ab73ad39c`. Casbin-CPP built with 74/74 tests passing on
  DevInstance4, commit `ce8c55ed1`. Two apt toolchains were too old for
  these projects (Maven 3.6.3, CMake 3.22.1) and were supplemented with
  newer local binaries (Maven 3.9.9, CMake 3.29.9) without touching the
  system-wide versions — see `docs/architecture.md` for why.
- **Step 4 (canonical corpus + adapters):** in progress. 10-scenario
  canonical corpus in the UOA course-score domain (a student's score in a
  specific course) covering Permit/Deny/NotApplicable, owner/role/
  department rules, numeric clearance comparison, time-of-day, network
  condition, and set-membership on action. **Middle Layer** and
  **AuthzForce Core** adapters are done and verified —
  `scripts/run-correctness.sh middle-layer` and `... authzforce` both run
  for real, **10/10 scenarios correct** on each, against the exact same
  reference XACML 3.0 policy (`corpus/reference-policies/xacml3-course-
  score-policy.xml`). One real interop bug found and fixed along the way:
  AuthzForce rejects the legacy XACML 1.0-namespaced `permit-overrides`
  combining-algorithm URN outright — switched to the XACML 3.0-namespaced
  one, which both engines accept. **SunXACML** is also done and verified:
  `scripts/run-correctness.sh sunxacml` runs for real, **10/10 scenarios
  correct**, against a hand-translated XACML 2.0 form of the same reference
  policy (`corpus/reference-policies/xacml2-course-score-policy.xml` —
  XACML 2.0 has no generic Category-attributed AttributeDesignator, so the
  Target/Condition syntax genuinely has to differ, using the native
  `1.0`-namespaced combining-algorithm URN, which is correct for XACML 2.0,
  not a downgrade). Getting SunXACML running at all required resolving a
  runtime-only dependency the pinned 2010-era jar needs but the JDK no
  longer ships: JAXB (`javax.xml.bind`), removed from the JDK in Java 9+.
  Pulled the full `org.glassfish.jaxb:jaxb-runtime:2.3.1` dependency tree
  via Maven into `/opt/abac-research/engine/jaxb-libs/`. **Casbin-CPP** is
  also done: `scripts/run-correctness.sh casbin-cpp` runs for real, **9/9
  supported scenarios correct** — Casbin has no per-rule Target/Rule
  structure or NotApplicable concept (`Enforce()` is strictly boolean), so
  the whole reference policy became one fixed `[matchers]` expression
  (`corpus/reference-policies/casbin-model.conf`), and the one scenario
  whose canonical answer is `NotApplicable` (abac-010) is honestly marked
  `supported: false` rather than forced into a fake Permit/Deny comparison.
  **All four adapters are now implemented and passing.** Policy-scale
  tiers (small/medium/large — see Step 5) are done; remaining Step 4 work
  is missing-attribute semantics, a deny-overrides/first-applicable
  demonstration, and obligations/advice, none of which need new adapters.
- **Step 5 (correctness + benchmarking):** 5A done, 5B first pass done.
  `scripts/run-correctness.sh <engine> [small|medium|large]` generates
  three policy-scale tiers per engine (0/1000/5000 decoy rules/rows,
  realistic and randomized — see below — that can never flip a real
  scenario's expected decision) and **correctness holds at 10/10 (9/9 for
  Casbin-CPP) at every scale, on all four engines** — 12/12 engine×scale
  combinations verified.

  Decoys draw from three structurally-varied, realistic shapes
  (role+network / department+clearance / action+hour) using real value
  pools (15 departments, 10 roles, etc.) via a fixed-seed RNG (260825,
  byte-identical across all four VMs), all `Effect="Deny"` so they're safe
  to let coincidentally match a real scenario under `permit-overrides` (a
  Deny-effect rule can never flip an expected Permit).

  **Step 5B**: a real manifest-driven protocol (`benchmark-manifest.conf`
  — warmup=5, measured=20, repetitions=3; deliberately small since
  AuthzForce's CLI has no batch mode and would take hours at guide-scale
  numbers; concurrency testing deferred). All four runners now support a
  `benchmark` mode: warm-up discarded, then `repetitions × measured`
  calls **round-robin across all 10 canonical scenarios** (not repeatedly
  sampling one Permit case, which short-circuits before ever reaching a
  policy's decoy rules — an early single-sample pass made exactly that
  mistake and showed a flat/noisy trend for SunXACML as a result), with
  per-call latency recorded to a raw TSV and median/mean/p95/p99/stddev/
  throughput/peak-RSS computed into a summary JSON. `scripts/run-
  benchmark.sh <engine> [scale]` runs the correctness gate first, then
  the benchmark. Full results (median / p95 / p99 latency, throughput,
  peak RSS):

  | Engine | Scale | Median | p95 | p99 | Throughput/s | Peak RSS |
  |---|---|---|---|---|---|---|
  | Middle Layer | small | 3.1 ms | 5.4 ms | 9.0 ms | 298 | 122 MB |
  | Middle Layer | medium | 22.8 ms | 33.1 ms | 36.5 ms | 41 | 433 MB |
  | Middle Layer | large | 200.7 ms | 310.8 ms | 413.4 ms | 4.4 | 1.35 GB |
  | SunXACML | small | 2.6 ms | 5.1 ms | 28.9 ms | 278 | 101 MB |
  | SunXACML | medium | 30.1 ms | 66.3 ms | 85.5 ms | 37 | 348 MB |
  | SunXACML | large | 156.9 ms | 174.2 ms | 247.1 ms | 9.9 | 584 MB |
  | Casbin-CPP | small | 0.14 ms | 0.18 ms | 0.19 ms | 6684 | 6.8 MB |
  | Casbin-CPP | medium | 1.48 ms | 3.43 ms | 3.63 ms | 697 | 7.1 MB |
  | Casbin-CPP | large | 7.10 ms | 7.18 ms | 11.75 ms | 197 | 7.7 MB |
  | AuthzForce* | small | 1.38 s | 1.45 s | 1.51 s | 0.72 | n/a |
  | AuthzForce* | medium | 2.47 s | 2.58 s | 2.76 s | 0.40 | n/a |
  | AuthzForce* | large | 4.40 s | 4.59 s | 4.75 s | 0.23 | n/a |

  \* AuthzForce's numbers are the whole subprocess wall time (JVM startup
  + policy load + evaluation, inseparable — no batch mode); not directly
  comparable to the other three's in-process figures. Its "peak RSS" is
  omitted (marked n/a) because the Python orchestrator measures its own
  `/proc/self/status`, not the actual Java subprocess doing the work — a
  known measurement bug, not a claim that AuthzForce uses ~12MB.

  Round-robin sampling produced a **clean, monotonic** scaling trend on
  every engine (unlike the earlier single-Permit-sample pass), and
  reconfirms Casbin-CPP's architectural lightness from the earlier
  discussion: 3 orders of magnitude less peak memory than the XML-based
  engines, consistent with plain-CSV parsing versus DOM tree construction.

  **Concurrency testing** (`concurrency_levels=1,2,4,8`, small scale only
  — medium/large × 4 levels would multiply AuthzForce's already-slow
  per-call JVM-spawn cost past a practical runtime for this session):

  | Engine | c=1 | c=2 | c=4 | c=8 |
  |---|---|---|---|---|
  | Middle Layer (req/s) | 246 | 492 | 941 | 1074 |
  | SunXACML (req/s) | 202 | 387 | 701 | 845 |
  | Casbin-CPP (req/s) | 2403 | 4449 | 6834 | 10238 |
  | AuthzForce (req/s) | 0.70 | 1.29 | 1.49 | 1.61 |

  Middle Layer and SunXACML share **one PDP instance across worker
  threads** (matching how a real long-running PDP service is actually hit
  by concurrent requests) — both scale well up to 4 threads with
  diminishing returns toward 8 (this VM has 8 vCPUs), and per-call median
  latency stays roughly flat, meaning the throughput gain is real
  parallelism, not queuing.

  **Casbin-CPP hit a real bug during this pass**: `casbin::Enforcer` is
  not thread-safe at all — sharing one instance across worker threads
  segfaulted at concurrency ≥ 2, and giving each thread its own
  independently-constructed instance *still* segfaulted at concurrency
  ≥ 2, pointing at global/static state inside the library (most likely
  the vendored Exprtk expression engine), not something fixable from the
  adapter side. Concurrency for this engine is therefore measured via
  independent OS processes instead (`run-casbin-benchmark.py`, same
  approach as AuthzForce) — confirmed zero crashes after the fix, with by
  far the best scaling of any engine (10,238 req/s at c=8) since each
  process only parses a tiny CSV rather than spinning up a JVM.

  AuthzForce improves only modestly (0.70 → 1.61 req/s) since 8 concurrent
  JVM spawns compete heavily for the same 8 vCPUs during startup — the
  per-call cost is dominated by JVM initialization, not evaluation, so
  concurrency helps far less here than for the in-process engines.

  **Not yet done:** guide-scale iteration counts (would require a faster
  AuthzForce invocation path — e.g. its embedded API instead of spawning
  the CLI — to be practical), concurrency at medium/large scale, fixing
  the AuthzForce/Casbin-CPP (process-based) peak-RSS measurement to target
  the actual worker processes rather than the orchestrator, and an
  independent check that concurrent evaluation doesn't silently corrupt
  *results* (not just crash) on Middle Layer/SunXACML — absence of a
  crash was treated as sufficient evidence for this pass, not proven.
- **Step 6 (aggregation + report):** not started.

See `docs/architecture.md` for the implementation architecture and
`docs/semantic-mapping.md` for how canonical ABAC semantics map onto each
engine.

## Non-negotiable experimental rules

1. Do not modify SSH, firewall, security groups, networking, user accounts, or
   Nectar configuration.
2. Do not delete or overwrite existing research data.
3. Inspect before changing; preserve unrelated existing files and services.
4. Record every installed package, source commit, artifact checksum, build
   command, runtime command, exit code, and error.
5. Pin inputs and source versions before benchmarking.
6. All systems use the same canonical semantic workload, not identical raw
   engine files.
7. Never change expected decisions merely to make an engine pass.
8. Mark cases as unsupported when their semantics cannot be represented
   faithfully.
9. Separate setup, correctness validation, warm-up, and measured benchmarking.
