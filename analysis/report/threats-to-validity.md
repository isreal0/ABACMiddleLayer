# Threats to Validity

## Measurement scale and statistical power

- **Small iteration counts.** 20 measured calls/worker × 3 repetitions is
  far below the master guide's suggested 10,000 — chosen because
  AuthzForce's CLI has no batch mode (every call is an independent JVM
  process, 1-5 seconds at the scales tested) and guide-scale iteration
  counts would take hours per engine per scale. Single-threaded latency/
  percentile figures in `performance.md` should be treated as indicative,
  not final; a guide-scale run would need either a much longer session or
  a faster AuthzForce invocation path (its embedded API instead of the
  CLI).
- **Concurrency tested at small policy scale only.** Medium/large × 4
  concurrency levels would multiply AuthzForce's already-slow per-call
  cost past what was practical to run in this session.
- **No dedicated warm-up beyond the manifest's 5 iterations**, and no
  repeated multi-hour runs to characterize run-to-run variance beyond the
  3 repetitions taken.

## Cloud/infrastructure noise

- No CPU pinning, no isolation guarantee from other tenants on the same
  Nectar hypervisor host. Single-sample and small-N measurements are more
  exposed to transient scheduling noise than a properly warmed, high-N
  run would be — visible in SunXACML's single-sample `evaluation_ns` not
  showing a clean trend before round-robin sampling was adopted (see
  `methodology.md`).
- All four VMs were used exclusively for this benchmark during the
  measurement windows, but background OS/kernel activity (cron, journald,
  etc.) was not suppressed or measured separately.

## Legacy software

- **SunXACML (2.0-M1) is unmaintained** (last released 2010) and required
  restoring JAXB to the classpath to run at all on a modern JDK (see
  `environment.md`). Its actual production use today is essentially nil;
  it's included here as the master guide's designated legacy XACML 2.0
  baseline, not as a claim that it represents current practice.

## Adapter effects

- **Decoy-rule information asymmetry.** XACML decoys carry full
  Target/Condition XML structure (~500 bytes each); Casbin-CPP's decoy
  rows are minimal placeholders (~40 bytes), because its static matcher
  never reads policy-row content at all — this is architecturally forced,
  not an oversight, but it means the "large" policy-size comparison
  across engines reflects each engine's actual on-disk policy
  representation faithfully, without being a byte-for-byte equal amount
  of information injected per rule. See the discussion in this project's
  working notes on why an `eval()`-based fix was considered and rejected
  (it would trade one asymmetry for a different, likely worse one —
  runtime expression recompilation per row per call, versus pre-parsed
  tree traversal).
- **AuthzForce and Casbin-CPP (process-based concurrency) peak-RSS
  figures are wrong by construction**: the Python orchestrator reports
  its own memory, not the worker subprocess's actual usage. Marked n/a /
  flagged rather than presented as real numbers anywhere in this report.
- **Concurrent correctness was not independently verified** for Middle
  Layer/SunXACML. Absence of a crash across all tested concurrency levels
  was treated as sufficient evidence that shared-instance concurrent
  access doesn't corrupt results — this is a reasonable but unproven
  assumption; a dedicated correctness-under-load check (comparing
  concurrent-run decisions against the known-correct single-threaded
  ones) was not built.

## Semantic-coverage limitations

- **10 scenarios** cover a meaningful but partial slice of ABAC/XACML
  semantics. Deliberately deferred rather than guessed at (see
  `docs/semantic-mapping.md` "Status" section in the harness repo):
  - Missing-attribute / Indeterminate semantics — XACML's rules for
    combining an Indeterminate rule result under `permit-overrides` are
    subtle and implementation-nuanced; asserting an `expected` value
    without an empirical cross-engine comparison pass first would risk
    encoding a wrong assumption as ground truth.
  - An explicit demonstration that `deny-overrides`/`first-applicable`
    change an outcome versus `permit-overrides` on the same conflicting
    rule set — the corpus uses `permit-overrides` throughout but has not
    yet shown the other two algorithms changing a result.
  - Datatype errors, obligations, and advice — not represented in any
    scenario yet.
- The legacy `policy1k`/`policy5k` directories found pre-existing in the
  Middle Layer's repository were **not** reused for scale testing (see
  `methodology.md`) because they were not produced by the governed
  canonical-corpus pipeline and could not be traced to a specific
  semantic intent; the decoy-rule mechanism described in `methodology.md`
  supersedes them.

## What would most change these results with more time

In rough priority order: (1) an embedded-API AuthzForce path to make
guide-scale iteration counts practical, (2) concurrency testing at
medium/large policy scale, (3) a dedicated concurrent-correctness check,
(4) fixing the two processes' peak-RSS measurement to target the actual
worker, (5) expanding the corpus to cover the deferred semantic gaps
above.
