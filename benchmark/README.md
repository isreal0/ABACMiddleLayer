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
  one, which both engines accept. **SunXACML** (needs XACML 2.0 syntax
  translation) and **Casbin-CPP** (different paradigm entirely) adapters
  are not built yet — that's what's left of Step 4.
- **Step 5 (correctness + benchmarking):** not started.
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
