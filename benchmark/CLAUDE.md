# CLAUDE.md — benchmark/

Repository-specific constraints for anyone (human or agent) working in this
`benchmark/` subtree, which coexists with the ABAC Middle Layer source
(`abacml/`, `postgres/`) in the same repository.

## Scope

This directory is engine-neutral: canonical scenarios, per-engine adapters,
schemas, and orchestration scripts. It does not contain engine source code.
Engine sources/builds live under `/opt/abac-research/engine` on each VM
(git-ignored — never commit built artifacts, JARs, or binaries here).

## Hard constraints (inherited from the master experiment guide)

- Never modify SSH, firewall, security groups, networking, user accounts, or
  Nectar configuration from any script in this directory.
- Never delete or overwrite files outside `/opt/abac-research/{results,logs,
  versions}` and this repo's own tracked paths.
- Never change an `expected` field in the canonical corpus to make an engine
  pass — mark the case `unsupported` instead and explain why in
  `docs/semantic-mapping.md`.
- Canonical corpus commit must match across all four VMs before any benchmark
  run. Scripts should read the commit from `/opt/abac-research/versions/
  corpus.commit` and fail loudly on mismatch, not silently proceed.

## Commands

```bash
scripts/capture-environment.sh          # dumps hardware/software versions
scripts/run-correctness.sh <engine>     # correctness-only, no timing claims
scripts/run-benchmark.sh <engine>       # controlled benchmark, consumes
                                         # a manifest (warmup/measured
                                         # iteration counts, concurrency)
```

`<engine>` values: `middle-layer`, `sunxacml`, `authzforce`, `casbin-cpp`.

## Where things live per VM

| VM | `/opt/abac-research/repo` | Notes |
|---|---|---|
| DevInstance (130.216.217.124) | symlink -> `~/project` | Full Middle Layer source (this repo) present locally |
| DevInstance2/3/4 | sparse checkout of this repo (`benchmark/` only) | Full `abacml`/`postgres` tree not needed/present |

## Known open architectural item

The original design notes referenced WSO2 Balana for the Middle Layer's PDP
integration; SunXACML is a separate baseline on DevInstance2, not a
substitute. `abacml/src/main/java/com/yasusoft/abacml/ABACML.java` is the JNI
entry point called from `postgres/src/backend/tcop/postgres.c`. Confirm which
XACML library `abacml/pom.xml` actually pins before writing
`docs/architecture.md`'s final "PDP choice" section (Step 2).
