#!/usr/bin/env python3
"""Benchmark runner for the AuthzForce Core adapter (Step 5B).

Usage: run-authzforce-benchmark.py <cli-jar> <generated-authzforce-dir> \
           <canonical-scenarios-json> <manifest-conf> <concurrency> <raw-output-tsv> <summary-output-json>

The CLI has no batch mode -- every call is a fresh, independent JVM
process, so "concurrency" here just means launching that many subprocess
calls in parallel (via a thread pool -- each worker thread blocks in
subprocess.run, releasing the GIL, so this achieves real OS-level
parallelism despite Python's GIL). Unlike the other three engines'
benchmark modes, there is no separate "policy load once, then measure hot
evaluations" phase: total_ns per call already includes JVM startup +
policy load + evaluation, inseparably. See benchmark/docs/semantic-mapping.md.
"""
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_authzforce_correctness_lib import run_one  # noqa: E402


def read_manifest(path):
    m = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            m[k.strip()] = v.strip()
    return m


def percentile(sorted_vals, p):
    idx = max(0, math.ceil(p * len(sorted_vals)) - 1)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def read_peak_rss_kb():
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return -1


def worker_run(cli_jar, pdp_xml, requests_dir, scenario_ids, worker_id, measured):
    n = len(scenario_ids)
    rows = []
    for i in range(measured):
        sid = scenario_ids[i % n]
        _actual, _error, total_ns = run_one(cli_jar, pdp_xml, os.path.join(requests_dir, f"{sid}.xml"))
        rows.append((worker_id, i, sid, total_ns))
    return rows


def main():
    if len(sys.argv) != 8:
        print("usage: run-authzforce-benchmark.py <cli-jar> <generated-authzforce-dir> "
              "<canonical-scenarios-json> <manifest-conf> <concurrency> <raw-output-tsv> <summary-output-json>",
              file=sys.stderr)
        return 2
    cli_jar, af_dir, canonical_path, manifest_path, concurrency_str, raw_output_tsv, summary_output_json = sys.argv[1:8]
    concurrency = int(concurrency_str)

    pdp_xml = os.path.join(af_dir, "pdp.xml")
    requests_dir = os.path.join(af_dir, "requests")

    with open(canonical_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
    scenario_ids = [s["id"] for s in scenarios]
    n = len(scenario_ids)

    manifest = read_manifest(manifest_path)
    warmup = int(manifest["warmup_iterations"])
    measured = int(manifest["measured_iterations"])
    repetitions = int(manifest["repetitions"])

    for i in range(warmup):
        sid = scenario_ids[i % n]
        run_one(cli_jar, pdp_xml, os.path.join(requests_dir, f"{sid}.xml"))

    all_rows = []
    total_wall_seconds = 0.0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for rep in range(repetitions):
            start = time.perf_counter()
            futures = [
                pool.submit(worker_run, cli_jar, pdp_xml, requests_dir, scenario_ids, w, measured)
                for w in range(concurrency)
            ]
            for fut in futures:
                all_rows.extend(fut.result())
            total_wall_seconds += time.perf_counter() - start

    with open(raw_output_tsv, "w", encoding="utf-8") as raw_out:
        raw_out.write("worker\titeration\tscenario_id\tlatency_ns\n")
        for worker_id, i, sid, total_ns in all_rows:
            raw_out.write(f"{worker_id}\t{i}\t{sid}\t{total_ns}\n")

    all_latencies = sorted(r[3] for r in all_rows)
    mean = statistics.mean(all_latencies)
    aggregate_throughput = len(all_latencies) / total_wall_seconds
    summary = {
        "engine": "authzforce",
        "concurrency": concurrency,
        "warmup_iterations": warmup,
        "measured_iterations_per_worker": measured,
        "repetitions": repetitions,
        "sample_count": len(all_latencies),
        "latency_ns": {
            "min": all_latencies[0],
            "median": statistics.median(all_latencies),
            "mean": round(mean),
            "p95": percentile(all_latencies, 0.95),
            "p99": percentile(all_latencies, 0.99),
            "max": all_latencies[-1],
            "stddev": round(statistics.pstdev(all_latencies)),
        },
        "aggregate_throughput_per_sec": aggregate_throughput,
        "peak_rss_kb": read_peak_rss_kb(),
        "notes": "total_ns includes JVM startup + policy load + evaluation, inseparable (CLI has no batch "
                 "mode); peak_rss_kb is this Python orchestrator's own RSS, not the Java subprocesses' -- known "
                 "measurement limitation, see semantic-mapping.md",
    }
    with open(summary_output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"AuthzForce benchmark (concurrency={concurrency}): {len(all_latencies)} measured calls, "
          f"aggregate throughput {aggregate_throughput}/s, summary written to {summary_output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
