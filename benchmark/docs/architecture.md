# Architecture

## Overview

Four independently-provisioned Ubuntu 22.04 VMs (Nectar `m3.large`: 8 vCPU,
16 GB RAM, 30 GB disk) each host one authorization system. One is the
implementation under evaluation (the ABAC Middle Layer); the other three are
independent baselines. All four consume the same canonical, engine-neutral
scenario corpus (Step 4) through a per-engine adapter, and report results in
one normalized schema (`schemas/result.schema.json`) so correctness and
performance are comparable across systems.

```
canonical scenarios (corpus/canonical, one Git commit, identical on all 4 VMs)
        |
        +--> Middle Layer adapter   --> DevInstance   (C/Postgres + JNI + XACML PDP)
        +--> SunXACML adapter       --> DevInstance2  (XACML 2.0)
        +--> AuthzForce adapter     --> DevInstance3  (XACML 3.0)
        +--> Casbin-CPP adapter     --> DevInstance4  (model.conf/policy.csv)
```

## ABAC Middle Layer (DevInstance) — as found

DevInstance was **not** a blank VM: it already carries prior implementation
work, checked out at `~/project` (this repository, remote
`github.com/isreal0/ABACMiddleLayer`) and symlinked into
`/opt/abac-research/repo`.

Call path (as documented by the repository owner):

```
PostgreSQL (postgres/src/backend/tcop/postgres.c, trigger point)
    -> C code
    -> JNI call into Balana  (abacml/src/main/java/com/yasusoft/abacml/ABACML.java)
    -> XACML policy evaluation
    -> decision returned to C code
    -> back to Postgres
```

Key paths inside `~/project`:

- `abacml/` — customized Java module, JNI entry point, Maven build
  (`abacml/pom.xml`).
- `postgres/` — modified PostgreSQL source tree (not vendored via submodule;
  merged directly into this repo's history).
- `data/` — PostgreSQL data directory (git-ignored).
- `abacmlpolicy.xml` / `abacml/resources/abacmlpolicy.xml` — XACML policy
  (the root-level copy is a runtime-generated duplicate; treated as a build
  artifact, git-ignored, and slated to be replaced by the canonically
  generated policy in Step 4).
- `generate_policy.c`, `generate_rule.c` (+ compiled `gpolicy`, `grule`) —
  legacy policy/rule generators; superseded by the canonical-corpus generator
  once Step 4 lands.

**Open item:** confirm from `abacml/pom.xml` which XACML implementation is
actually pinned (design notes mention WSO2 Balana; do not assume this without
checking, and do not conflate it with SunXACML, which is the separate
DevInstance2 baseline). Record the finding and justification here once
verified (Step 2).

## Baselines — as found

DevInstance2/3/4 were freshly provisioned (empty home directories, no extra
packages beyond the base image) at the time of Step 0. Each gets its engine
installed independently in Step 3, isolated from the others.

## Shared harness layout (this repo's `benchmark/` + each VM's `/opt/abac-research`)

```
/opt/abac-research/
├── repo/                 # engine source: symlink on DevInstance, sparse
│                         #   checkout of this repo (benchmark/ only)
│                         #   elsewhere
├── corpus/
│   ├── canonical/        # engine-neutral scenarios (Step 4)
│   └── generated/        # native files generated per engine (build artifact)
├── engine/               # engine source/build output (git-ignored)
├── harness/              # this benchmark/ subtree, checked out per VM
├── results/{raw,normalized,compatibility}/
├── logs/
└── versions/             # captured environment + pinned commit/checksum info
```

## PDP / library choices — decision log

| Engine | Library | Version/commit | Justification |
|---|---|---|---|
| Middle Layer | TBD (Balana vs. other) | TBD | Pending inspection of `abacml/pom.xml` (Step 2) |
| SunXACML baseline | `net.sf.sunxacml:sunxacml` | `2.0-M1` (pinned JAR) | Specified by the master guide as the legacy XACML 2.0 baseline |
| AuthzForce baseline | `authzforce/core` | TBD (pin at clone time) | Specified by the master guide as the modern XACML 3.0 baseline |
| Casbin-CPP baseline | `apache/casbin-cpp` | TBD (pin at clone time) | Specified by the master guide as the embedded PERM-model baseline |
