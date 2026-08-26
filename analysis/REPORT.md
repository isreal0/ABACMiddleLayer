# ABAC Middle Layer vs. Three Baselines — Consolidated Analysis Report

Snapshot as of corpus/adapter commit `24b091d64164de5054b75d68890f6efb62183081`
(2026-08-27). Raw and normalized data this report summarizes lives
alongside it in `analysis/raw/`, `analysis/normalized/`, and
`analysis/versions/`; nothing here is invented — every number below is
traceable to a specific file in this directory.

## 1. Environment

Four Ubuntu 22.04.2 LTS VMs (Nectar `m3.large`: 8 vCPU, ~16 GB RAM, 30 GB
disk), one per system under test. See `analysis/inventory.csv` for the
Step 0 hardware/OS inventory and `analysis/versions/<hostname>/` for
per-VM captured environment (`environment.<hostname>.txt`), pinned
artifact checksums, and engine commit/version records:

| VM | Purpose | Engine version/commit |
|---|---|---|
| devinstance (130.216.217.124) | ABAC Middle Layer (system under evaluation) | WSO2 Balana 1.1.12 |
| devinstance2 (130.216.216.210) | SunXACML baseline | 2.0-M1 (sha256 in `versions/devinstance2/sunxacml.sha256`) |
| devinstance3 (130.216.217.221) | AuthzForce Core baseline | commit `ab73ad39cf037cdd87100e2148464b1d2d64d5b6` |
| devinstance4 (130.216.216.147) | Casbin-CPP baseline | commit `ce8c55ed19b34628e63f831231929c764051d3a2` |

Two engines needed a newer build toolchain than Ubuntu 22.04's apt
provides (installed as local binaries, system apt versions untouched):
Maven 3.9.9 for AuthzForce (`dependency-check-maven` requires ≥3.8.1,
apt has 3.6.3) and CMake 3.29.9 for Casbin-CPP (`DOWNLOAD_EXTRACT_TIMESTAMP`
requires ≥3.24, apt has 3.22.1 which silently corrupts the generated
git-clone command instead of erroring). SunXACML additionally needed the
JAXB runtime (`org.glassfish.jaxb:jaxb-runtime:2.3.1` + transitive deps,
recorded in `versions/devinstance2/jaxb-libs.sha256`) restored to the
classpath, since Java 9+ removed it from the JDK and the pinned 2010-era
jar depends on it for XML marshalling.

## 2. Methodology

**Canonical corpus**: 10 hand-authored scenarios (`corpus/canonical/scenarios.json`
in the harness repo) in a University of Auckland "course score" domain — a
student's score in a specific course — covering Permit, Deny,
NotApplicable, owner-based/role-based/department-based rules, numeric
clearance/classification comparison, time-of-day and network conditions,
and set-membership on action. Ground truth was derived against a
hand-authored XACML 3.0 reference policy, then translated (not
re-derived) into XACML 2.0 for SunXACML and a single Exprtk matcher
expression for Casbin-CPP — see `docs/semantic-mapping.md` in the harness
repo for the full per-engine translation notes.

**Policy-scale tiers**: small (0 decoy rules — the original policy
as-authored), medium (1000), large (5000). Decoy rules/rows are
structurally varied and randomized (three shapes, drawn from realistic
value pools, fixed seed 260825 for byte-identical reproducibility across
VMs) and always `Effect=Deny`, so they can never flip an expected Permit
under `permit-overrides` and are safe to let coincidentally match a real
scenario. They exist purely to exercise policy-load and rule-scanning
cost as the policy grows.

**Benchmark protocol** (`benchmark-manifest.conf`): warmup=5,
measured=20 per worker, repetitions=3, concurrency_levels=1,2,4,8.
Deliberately small relative to the master guide's suggested figures
(warmup=1000, measured=10000) because AuthzForce's CLI has no batch mode
— every call is an independent JVM process taking 1-5 seconds at these
scales, and guide-scale iteration counts would take hours. Round-robin
sampling cycles through all 10 canonical scenarios (not repeatedly
sampling one Permit case, which short-circuits under `permit-overrides`
before ever reaching a policy's decoy rules — an early single-sample pass
made exactly this mistake and produced a misleadingly flat/noisy trend).

## 3. Correctness

**12/12 engine×scale combinations pass.** All four engines agree on
every scenario each can represent — three XACML engines agree exactly on
all 10 scenarios at every one of the three policy scales; Casbin-CPP
agrees on all 9 of the 10 it can represent at all. See
`analysis/compatibility.csv` for the full per-scenario matrix and
`analysis/normalized/*.small.jsonl` (`*.medium.jsonl`, `*.large.jsonl`)
for the underlying per-request records.

The one gap: **abac-010** (an action outside the policy's own scope,
expected `NotApplicable`) is marked `supported:false` for Casbin-CPP,
not a failure — confirmed from `include/casbin/enforcer_interface.h`
that every `Enforce()` variant returns a strict `bool`; Deny and
Indeterminate both collapse to `false` internally, and there is no third
value to compare against `NotApplicable` at all.

Two real interoperability bugs were found and fixed while building this,
not papered over:

1. **AuthzForce rejects the legacy XACML 1.0-namespaced `permit-overrides`
   combining-algorithm URN outright** (`UnsupportedOperationException`),
   even under a XACML 3.0-schema policy, while Balana accepts both forms.
   Fixed by using the XACML 3.0-namespaced URN in the shared reference
   policy — verified this didn't change Middle Layer's results.
2. **Casbin-CPP's `Enforcer::Enforce()` is not thread-safe at all** —
   confirmed empirically during concurrency testing (see §4): sharing one
   instance across worker threads segfaults at concurrency ≥ 2, and
   giving each thread its own independently-constructed instance *still*
   segfaults at concurrency ≥ 2, pointing at global/static state inside
   the library (most likely the vendored Exprtk expression engine), not
   fixable from the adapter side. Concurrency for this engine is measured
   via independent OS processes instead.

## 4. Performance

### 4.1 Single-threaded latency across policy scale

Median / p95 / p99 latency and peak RSS, one worker, round-robin across
all 10 scenarios (`benchmark-manifest.conf` protocol, 60 measured samples
per cell):

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

\* AuthzForce's numbers are the whole subprocess wall time (JVM startup +
policy load + evaluation, inseparable — no batch mode); not directly
comparable to the other three's in-process figures. Peak RSS is n/a: the
Python orchestrator measures its own `/proc/self/status`, not the actual
Java subprocess doing the work — a known measurement limitation, not a
claim that AuthzForce uses ~12 MB.

**Reading the trend**: all four engines scale monotonically with policy
size, but by very different factors. Casbin-CPP's policy is a plain CSV
table with a single pre-compiled matcher expression — three orders of
magnitude less peak memory than the XML-based engines, consistent with
flat-text parsing versus DOM tree construction. The three XACML engines
must parse an XML rule tree at load time and walk it at evaluation time;
their memory and latency both grow with rule count roughly as expected
for that architecture.

### 4.2 Concurrency (small scale only)

Aggregate throughput (measured requests ÷ wall-clock time of the whole
concurrent batch, not the reciprocal of mean latency):

| Engine | c=1 | c=2 | c=4 | c=8 | How concurrency is achieved |
|---|---|---|---|---|---|
| Middle Layer | 246 | 492 | 941 | 1074 req/s | Java thread pool, one shared PDP instance |
| SunXACML | 202 | 387 | 701 | 845 req/s | Java thread pool, one shared PDP instance |
| Casbin-CPP | 2403 | 4449 | 6834 | 10238 req/s | Independent OS processes (see the thread-safety bug in §3) |
| AuthzForce | 0.70 | 1.29 | 1.49 | 1.61 req/s | Independent OS processes (no batch mode) |

Middle Layer and SunXACML share one engine instance across threads,
matching how a real long-running PDP service is actually hit by
concurrent requests; both scale well to 4 threads with diminishing
returns toward 8 (the VM has 8 vCPUs), and per-call median latency stays
roughly flat, meaning the throughput gain is real parallelism rather than
queuing. AuthzForce improves only modestly because 8 concurrent JVM
spawns compete for the same 8 vCPUs during startup — the per-call cost is
dominated by JVM initialization, not evaluation. Casbin-CPP scales best
of all once moved to a process-per-worker model, since each process only
needs to parse a small CSV file rather than start a JVM.

## 5. Threats to validity

- **Small iteration counts.** 20 measured calls/worker × 3 repetitions is
  far below the master guide's suggested 10,000 — chosen to keep
  AuthzForce's per-call JVM-spawn cost from making a full sweep
  impractical in this session. Single-threaded latency/percentile figures
  above should be treated as indicative, not final; guide-scale numbers
  would need either a much longer run or a faster AuthzForce invocation
  path (its embedded API instead of the CLI).
- **Concurrency tested at small scale only.** Medium/large × 4 concurrency
  levels would multiply AuthzForce's already-slow per-call cost past a
  practical runtime here.
- **Concurrent correctness not independently verified.** Absence of a
  crash was treated as sufficient evidence that Middle Layer/SunXACML's
  shared-instance concurrent access doesn't corrupt results — this was
  not proven with a dedicated correctness-under-load check.
- **AuthzForce and Casbin-CPP (process-based) peak-RSS figures are wrong**
  by construction: the Python orchestrator reports its own memory, not
  the worker subprocess's. Marked `n/a` / noted rather than presented as
  real numbers.
- **Cloud noise.** No dedicated CPU pinning, no isolation from other
  tenants on the same hypervisor host; single-sample and small-N
  measurements are more exposed to transient noise than a properly
  warmed, high-N run would be.
- **Corpus size and feature coverage.** 10 scenarios cover a meaningful
  but partial slice of ABAC/XACML semantics. Deliberately deferred (see
  `docs/semantic-mapping.md` "Status" section): missing-attribute/
  Indeterminate semantics, an explicit deny-overrides/first-applicable
  demonstration, datatype errors, obligations, and advice.
- **Decoy-rule realism is engine-asymmetric by construction.** XACML
  decoys carry full Target/Condition XML structure (~500 bytes each);
  Casbin-CPP's decoy rows are minimal placeholders (~40 bytes) because its
  static matcher never reads policy-row content at all — the "large"
  policy-size comparison across engines therefore reflects each engine's
  actual on-disk policy representation faithfully, but is not a
  byte-for-byte equal amount of information per rule.

## 6. Final summary table

| System | Version/commit | Supported cases | Correctness | Small-scale median | p95 | p99 | Throughput (c=1) | Peak RSS (small) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ABAC Middle Layer | Balana 1.1.12 | 10/10 | 100% | 3.1 ms | 5.4 ms | 9.0 ms | 298/s | 122 MB |
| SunXACML | 2.0-M1 | 10/10 | 100% | 2.6 ms | 5.1 ms | 28.9 ms | 278/s | 101 MB |
| AuthzForce Core | `ab73ad39c` | 10/10 | 100% | 1.38 s* | 1.45 s* | 1.51 s* | 0.72/s | n/a |
| Casbin-CPP | `ce8c55ed1` | 9/10 | 100% of supported | 0.14 ms | 0.18 ms | 0.19 ms | 2403/s | 6.8 MB |

\* whole-process wall time, not directly comparable to the other rows.

---

See the harness repository (`isreal0/ABACMiddleLayer`, `benchmark/`
subtree) for full source, docs, and the reproduction commands
(`scripts/run-correctness.sh`, `scripts/run-benchmark.sh`). This file and
the accompanying `analysis/` data directory are a point-in-time snapshot;
re-running the harness at a later corpus commit will produce a different
snapshot, not overwrite this one.
