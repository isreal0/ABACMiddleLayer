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
- **Step 5 (correctness + benchmarking):** in progress.
  `scripts/run-correctness.sh <engine> [small|medium|large]` generates
  three policy-scale tiers per engine (0/1000/5000 decoy rules/rows that
  can never match a real scenario) and **correctness holds at 10/10 (9/9
  for Casbin-CPP) at every scale, on all four engines** — 12/12
  engine×scale combinations verified. Every runner now records real
  `policy_load_ns`/`evaluation_ns` (previously null placeholders) instead
  of fabricated timing. First look at the scaling signal (single-sample,
  not yet averaged over repeated iterations — see caveat below):

  | Engine | small load | medium load | large load |
  |---|---|---|---|
  | Middle Layer | 171 ms | 261 ms | 458 ms |
  | SunXACML | 93 ms | 205 ms | 490 ms |
  | Casbin-CPP | 0.4 ms | 2.0 ms | 7.4 ms |
  | AuthzForce (total, no batch mode) | 1.56 s | 2.09 s | 3.33 s |

  Casbin-CPP's policy files are trivially cheap to parse (plain CSV) next
  to the three XML-based engines. AuthzForce's numbers are the whole
  subprocess wall time (JVM startup + load + eval, inseparable — it has no
  batch mode, see `semantic-mapping.md`), not a clean load-only figure, so
  it isn't directly comparable to the other three's load-only column.
  **Caveat:** these are single samples per tier, not the guide's proper
  warmup/measured-iteration protocol — SunXACML's `evaluation_ns` in
  particular didn't show a clean trend on one sample (JIT/cache noise),
  which is exactly why Step 5B calls for averaging over many iterations
  rather than trusting one data point. That protocol (benchmark manifest,
  concurrency levels, percentiles) hasn't been built yet.
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
