# Performance

All figures traced to `analysis/normalized/*.benchmark.json` and
`analysis/raw/<engine>/*.tsv`. See `methodology.md` for protocol details
and `threats-to-validity.md` for what these numbers do and don't support.

## Single-threaded latency and memory across policy scale

Round-robin across all 10 scenarios, 60 measured samples per cell
(20 measured_iterations × 3 repetitions), concurrency=1:

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

\* Whole subprocess wall time (JVM startup + policy load + evaluation,
inseparable — no batch mode), not directly comparable to the other
three's in-process figures. Peak RSS is n/a: the Python orchestrator
measures its own `/proc/self/status`, not the Java subprocess doing the
work — a known measurement limitation, not a claim AuthzForce uses ~12 MB.

**Interpretation**: all four engines scale monotonically with policy
size, by very different factors. Casbin-CPP's policy is a plain CSV table
behind one pre-compiled matcher expression — three orders of magnitude
less peak memory than the XML-based engines, consistent with flat-text
parsing versus DOM tree construction, not merely "Casbin is faster" in
some engine-agnostic sense (see the note on decoy-rule information
asymmetry in `threats-to-validity.md`). The three XACML engines parse an
XML rule tree at load time and walk it at evaluation time; growth in both
memory and latency tracks rule count as expected for that architecture.

## Concurrency (small scale only)

Aggregate throughput = measured requests ÷ wall-clock time of the whole
concurrent batch:

| Engine | c=1 | c=2 | c=4 | c=8 | Mechanism |
|---|---|---|---|---|---|
| Middle Layer | 246 | 492 | 941 | 1074 req/s | Java thread pool, one shared PDP instance |
| SunXACML | 202 | 387 | 701 | 845 req/s | Java thread pool, one shared PDP instance |
| Casbin-CPP | 2403 | 4449 | 6834 | 10238 req/s | Independent OS processes |
| AuthzForce | 0.70 | 1.29 | 1.49 | 1.61 req/s | Independent OS processes |

Middle Layer and SunXACML share one instance across worker threads
(matching how a real long-running PDP service is actually hit by
concurrent requests): both scale well to 4 threads with diminishing
returns toward 8 (the VM has 8 vCPUs), and per-call median latency stays
roughly flat — the throughput gain is real parallelism, not queuing.
AuthzForce improves only modestly because 8 concurrent JVM spawns compete
for the same 8 vCPUs during startup; its per-call cost is dominated by
JVM initialization, not evaluation. Casbin-CPP, once moved to a
process-per-worker model (see `correctness.md` for why), scales best of
any engine — each process only parses a small CSV rather than starting a
JVM.
