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
- **Step 1 (workspace + this harness scaffold):** in progress.
- **Step 2 (Middle Layer implementation review/build):** not started.
- **Step 3 (baseline installs):** not started.
- **Step 4 (canonical corpus + adapters):** not started.
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
