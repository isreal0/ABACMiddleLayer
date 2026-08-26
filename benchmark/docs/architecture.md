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
        +--> Middle Layer adapter   --> DevInstance   (C/Postgres + JNI + Balana XACML PDP)
        +--> SunXACML adapter       --> DevInstance2  (XACML 2.0)
        +--> AuthzForce adapter     --> DevInstance3  (XACML 3.0)
        +--> Casbin-CPP adapter     --> DevInstance4  (model.conf/policy.csv)
```

## ABAC Middle Layer (DevInstance) — as found (confirmed by source inspection, Step 2)

DevInstance was **not** a blank VM: it already carries prior implementation
work, checked out at `~/project` (this repository, remote
`github.com/isreal0/ABACMiddleLayer`) and symlinked into
`/opt/abac-research/repo`.

### PDP library: WSO2 Balana 1.1.12 (confirmed, not SunXACML)

`abacml/pom.xml` pins `org.wso2.balana:org.wso2.balana:1.1.12` (plus
`org.wso2.balana.utils`, `xercesImpl-2.8.1.wso2v2`, `commons-logging`). This
matches the original design notes and is **distinct from SunXACML**, which
remains the separate, isolated DevInstance2 baseline — the two were never
conflated.

### Call path (confirmed from source, `postgres/src/backend/tcop/postgres.c` ~line 4630 and `abacml/src/main/java/com/yasusoft/abacml/ABACML.java`)

```
PostgresMain(), simple-query path ('Q' message)
  -> JNI_CreateJavaVM with -Djava.class.path=/home/ubuntu/project/abacml/target/abacml-dev.jar
     (first query per backend process; JNI_EEXIST -> JNI_GetCreatedJavaVMs +
      AttachCurrentThread on subsequent queries in the same backend — this
      reuse was added specifically to avoid repeated-JVM-creation crashes,
      per commit "Updated JVM invocation code to avoid jvm crash")
  -> FindClass("com/yasusoft/abacml/ABACML")
     GetStaticMethodID("Check_ABAC_Permission", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Z")
  -> Check_ABAC_Permission(subjectName, action, uri)
       -> initBalana(): sets FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY
          to abacml/resources (hardcoded absolute path), Balana.getInstance()
       -> createXACMLRequest(name, action, uri): builds a fixed XACML 3.0
          <Request> with exactly three attributes — subject-id, action-id,
          resource-id (all xs:string) — no environment category, no
          role/department/clearance/owner/classification attributes
       -> PDP.evaluate(request) -> ResponseCtx -> first Result's decision
       -> returns **boolean**: true iff decision == Permit; Deny,
          NotApplicable, and Indeterminate all collapse to false
  -> boolean result returned across JNI to postgres.c
```

Request construction on the C side (same function, after the JNI call site):
the SQL verb is extracted from the raw query string (uppercased, first
whitespace-delimited token) and used as `action`; `resource` is
`"/UOA_CANVAS_LMS/" + dbname` — i.e. **authorization granularity is
per-database, not per-table or per-row**, and the `UOA_CANVAS_LMS` prefix is
hardcoded from the implementation's original use case (a university LMS
scenario), not general-purpose.

The policy currently on disk (`abacml/resources/abacmlpolicy.xml`, tracked)
is a single first-applicable rule: `subject-id == "ubuntu"` -> Permit
(unconditional, on any action/resource). It is a smoke-test policy, not a
representative ABAC ruleset.

### Gap vs. the canonical corpus model (must be closed in Step 2, before Step 4 adapters can be written)

The master guide's canonical scenario format (subject role/department/
clearance, resource owner/department/classification, environment
network/hour, and Permit/Deny/NotApplicable/Indeterminate decisions) is
**not yet representable** by the current Middle Layer:

1. **Attribute model.** `createXACMLRequest` must be extended to carry the
   full canonical attribute set (subject, resource, and environment
   categories), not just three id strings.
2. **Decision fidelity.** `Check_ABAC_Permission`'s boolean return type must
   be replaced (or paralleled by a new method) that surfaces the actual
   XACML decision (Permit/Deny/NotApplicable/Indeterminate) end-to-end
   through the JNI boundary, so the harness can normalize it per
   `schemas/result.schema.json` instead of losing information at the
   Deny/NotApplicable/Indeterminate boundary.
3. **Resource granularity.** The database-level-only resource identifier
   (`/UOA_CANVAS_LMS/<dbname>`) cannot represent per-resource attributes
   (owner, department, classification) required by the corpus; this needs a
   generalized resource-attribute path independent of the LMS-specific
   prefix.
4. **Portability.** Policy directory and classpath are hardcoded absolute
   paths (`/home/ubuntu/project/...`) baked into both the Java source and
   `postgres.c`. Fine for a single-VM proof of concept; will need
   parameterization (env var or config file) so the benchmark harness can
   drive it without editing source.
5. **Policy generation.** The one on-disk policy is a hand-written smoke
   test. Step 4's canonically-generated XACML policies (from
   `corpus/canonical`) will replace it as the actual test input — the
   legacy `generate_policy.c`/`generate_rule.c`/`gpolicy`/`grule` tools and
   `policy1k`/`policy5k` directories are earlier, ungoverned attempts at
   this and are superseded, not extended.

None of the above has been changed yet — this section only records what
Step 2 inspection found. No code has been modified in `abacml/` or
`postgres/` as part of this survey.

## Baselines — as found, then built (Step 3)

DevInstance2/3/4 were freshly provisioned (empty home directories, no extra
packages beyond the base image) at the time of Step 0. Step 3 installed each
engine independently, isolated from the others:

- **SunXACML (DevInstance2):** OpenJDK 11.0.32 + Maven 3.6.3 + Ant installed.
  Pinned JAR `sunxacml-2.0-M1.jar` downloaded from SourceForge, verified as a
  valid ZIP/JAR containing the `com.sun.xacml` package tree, sha256 recorded
  at `/opt/abac-research/versions/sunxacml.sha256`.
- **AuthzForce Core (DevInstance3):** OpenJDK 17.0.20 installed. The apt
  Maven (3.6.3) could not build this project — `org.owasp:dependency-check-
  maven:13.0.0` requires Maven ≥3.8.1 — so Maven 3.9.9 was installed as a
  local binary under `/opt/abac-research/engine/apache-maven-3.9.9`
  (sha256 recorded), leaving the system `mvn` untouched. Even with 3.9.9,
  the OWASP dependency-check plugin still failed (`Invalid API Key` — it
  needs a registered NVD API key we don't have and won't provision, since
  it's a vulnerability-scan step unrelated to building/running the PDP).
  Built with `-Ddependency-check.skip=true`; all 5 reactor modules
  (`core`, `pdp-engine`, `pdp-io-xacml-json`, `pdp-testutils`, `pdp-cli`)
  report `SUCCESS`. Commit pinned at `ab73ad39cf037cdd87100e2148464b1d2d64d5b6`,
  full `mvn dependency:tree` recorded at
  `/opt/abac-research/versions/authzforce-core.dependencies.txt`.
- **Casbin-CPP (DevInstance4):** build-essential/cmake/ninja/boost installed.
  The apt CMake (3.22.1) generates a corrupted git-clone command for the
  `nlohmann/json` FetchContent dependency — `FetchContent_Declare(... 
  DOWNLOAD_EXTRACT_TIMESTAMP FALSE)` requires CMake ≥3.24 for that keyword
  to be parsed correctly; under 3.22 the generated script passes
  `DOWNLOAD_EXTRACT_TIMESTAMP` as the git `--origin` value and a garbage
  string as `WORKING_DIRECTORY`, so every clone attempt failed identically
  (initially misdiagnosed as network flakiness — a direct `git clone` of
  the same URL succeeded fine, which is what pointed at the generated
  script itself rather than the network). Fixed the same way as the Maven
  case: CMake 3.29.9 installed as a local binary under
  `/opt/abac-research/engine/cmake-3.29.9-linux-x86_64` (sha256 recorded),
  apt's cmake untouched. Commit pinned at
  `ce8c55ed19b34628e63f831231929c764051d3a2`. Build + full test suite:
  **74/74 tests pass**.

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
| Middle Layer | WSO2 Balana | `1.1.12` (confirmed via `abacml/pom.xml`) | Matches original design notes; distinct from SunXACML (DevInstance2 baseline) |
| SunXACML baseline | `net.sf.sunxacml:sunxacml` | `2.0-M1` (pinned JAR, sha256 in `versions/sunxacml.sha256`) | Specified by the master guide as the legacy XACML 2.0 baseline |
| AuthzForce baseline | `authzforce/core` | commit `ab73ad39cf037cdd87100e2148464b1d2d64d5b6` | Specified by the master guide as the modern XACML 3.0 baseline; built successfully with Maven 3.9.9 |
| Casbin-CPP baseline | `apache/casbin-cpp` | commit `ce8c55ed19b34628e63f831231929c764051d3a2` | Specified by the master guide as the embedded PERM-model baseline; built with CMake 3.29.9, 74/74 tests pass |

## Toolchain pins beyond apt (Step 3)

Two of the three baselines needed a newer build tool than Ubuntu 22.04's apt
repository provides. Both were installed as local binaries under each VM's
own `/opt/abac-research/engine/`, leaving the system-wide apt-installed
tool untouched, so nothing outside this project's own build directories was
modified:

| VM | Tool | apt version (insufficient) | Installed instead | Why |
|---|---|---|---|---|
| DevInstance3 | Maven | 3.6.3 | 3.9.9 (local binary) | `dependency-check-maven:13.0.0` requires Maven ≥3.8.1 |
| DevInstance4 | CMake | 3.22.1 | 3.29.9 (local binary) | `DOWNLOAD_EXTRACT_TIMESTAMP` in `FetchContent_Declare` requires CMake ≥3.24; under 3.22 it corrupts the generated git-clone command instead of failing with a version-check error |
