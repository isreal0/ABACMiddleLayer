# Environment

Snapshot as of corpus/adapter commit `47b4300c30288c9ec53f621fdc5bf5f2ed0c793a`
(2026-08-27). Full per-VM captures live in `analysis/versions/<hostname>/`;
this file summarizes them.

## Hardware and OS (Step 0)

Four Ubuntu 22.04.2 LTS VMs, Nectar `m3.large` flavor (8 vCPU, ~16 GB RAM,
30 GB root disk). See `analysis/inventory.csv` for the full Step 0 capture
(checked at 2026-08-26T07:14-07:15Z).

| Hostname | Public IP | Purpose |
|---|---|---|
| devinstance | 130.216.217.124 | ABAC Middle Layer (system under evaluation) |
| devinstance2 | 130.216.216.210 | SunXACML baseline |
| devinstance3 | 130.216.217.221 | AuthzForce Core baseline |
| devinstance4 | 130.216.216.147 | Casbin-CPP baseline |

## Engine versions / commits

| Engine | Version / commit | Source |
|---|---|---|
| Middle Layer PDP | WSO2 Balana 1.1.12 | `abacml/pom.xml` |
| SunXACML | `2.0-M1` (pinned JAR) | `analysis/versions/devinstance2/sunxacml.sha256` |
| AuthzForce Core | `ab73ad39cf037cdd87100e2148464b1d2d64d5b6` | `analysis/versions/devinstance3/authzforce-core.commit` |
| Casbin-CPP | `ce8c55ed19b34628e63f831231929c764051d3a2` | `analysis/versions/devinstance4/casbin-cpp.commit` |

## Toolchain gaps vs. apt, and how they were closed

Two engines needed a newer build tool than Ubuntu 22.04's apt repository
provides. Both were installed as local binaries under each VM's own
`/opt/abac-research/engine/`, leaving the system-wide apt-installed tool
untouched:

| VM | Tool | apt version (insufficient) | Installed instead | Why |
|---|---|---|---|---|
| devinstance3 | Maven | 3.6.3 | 3.9.9 (`analysis/versions/devinstance3/maven-3.9.9.sha256`) | `org.owasp:dependency-check-maven:13.0.0` requires Maven ≥3.8.1 |
| devinstance4 | CMake | 3.22.1 | 3.29.9 (`analysis/versions/devinstance4/cmake-3.29.9.sha256`) | `DOWNLOAD_EXTRACT_TIMESTAMP` in `FetchContent_Declare` requires CMake ≥3.24; under 3.22 it silently corrupts the generated git-clone command instead of raising a clear version-check error |

SunXACML additionally needed a runtime dependency put back on the
classpath: the pinned 2010-era jar's request/response marshalling is
JAXB-based (`javax.xml.bind`), which the JDK shipped built-in through
Java 8 but removed entirely in Java 9+. Resolved by pulling the full
`org.glassfish.jaxb:jaxb-runtime:2.3.1` dependency tree via Maven into
`/opt/abac-research/engine/jaxb-libs/` (checksums in
`analysis/versions/devinstance2/jaxb-libs.sha256`).

## Pre-existing state found on devinstance (Step 0/2)

`devinstance` was not a blank VM: `~/project` (this repository's working
copy) already contained prior implementation work — a Java/Maven module
(`abacml/`) with WSO2 Balana already as a dependency, and a vendored
PostgreSQL source tree (`postgres/`) with a JNI integration point in
`postgres/src/backend/tcop/postgres.c`. This was inspected, reconciled
into git (uncommitted local changes were committed rather than
discarded), and extended rather than replaced — see the harness repo's
`docs/architecture.md` for the full inspection record.
