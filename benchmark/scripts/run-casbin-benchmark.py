#!/usr/bin/env python3
"""Concurrency-safe benchmark orchestrator for the Casbin-CPP adapter (Step 5B).

casbin::Enforcer is not safe for concurrent use from multiple threads in one
process -- confirmed empirically: it segfaults at concurrency >= 2 even when
each thread has its own independently-constructed Enforcer instance, which
points at global/static state inside the library (likely the vendored
Exprtk expression engine), not per-instance state. See
benchmark/docs/semantic-mapping.md.

So unlike the in-process thread-pool approach used for Middle Layer and
SunXACML, concurrency here means launching independent OS processes of the
compiled `casbin_corpus_runner benchmark-worker` binary -- the same
process-based approach already used for AuthzForce, just with a real
binary instead of a JVM per call.

Usage: run-casbin-benchmark.py <runner-bin> <modelConf> <policyCsv> <scenariosTsv> \
           <manifest-conf> <concurrency> <raw-output-tsv> <summary-output-json>
"""
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor


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


def run_worker(runner_bin, model_conf, policy_csv, scenarios_tsv, measured, worker_id, tmp_dir):
    raw_path = os.path.join(tmp_dir, f"worker-{worker_id}.tsv")
    subprocess.run(
        [runner_bin, "benchmark-worker", model_conf, policy_csv, scenarios_tsv, str(measured), raw_path],
        check=True, capture_output=True, text=True,
    )
    rows = []
    with open(raw_path, "r", encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            i, sid, latency_ns = line.rstrip("\n").split("\t")
            rows.append((worker_id, int(i), sid, int(latency_ns)))
    return rows


def main():
    if len(sys.argv) != 9:
        print("usage: run-casbin-benchmark.py <runner-bin> <modelConf> <policyCsv> <scenariosTsv> "
              "<manifest-conf> <concurrency> <raw-output-tsv> <summary-output-json>", file=sys.stderr)
        return 2
    runner_bin, model_conf, policy_csv, scenarios_tsv, manifest_path, concurrency_str, raw_output_tsv, summary_output_json = sys.argv[1:9]
    concurrency = int(concurrency_str)

    manifest = read_manifest(manifest_path)
    warmup = int(manifest["warmup_iterations"])
    measured = int(manifest["measured_iterations"])
    repetitions = int(manifest["repetitions"])

    with tempfile.TemporaryDirectory() as tmp_dir:
        # single-process warm-up, discarded
        if warmup > 0:
            run_worker(runner_bin, model_conf, policy_csv, scenarios_tsv, warmup, "warmup", tmp_dir)

        all_rows = []
        total_wall_seconds = 0.0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for rep in range(repetitions):
                start = time.perf_counter()
                futures = [
                    pool.submit(run_worker, runner_bin, model_conf, policy_csv, scenarios_tsv, measured, f"{rep}-{w}", tmp_dir)
                    for w in range(concurrency)
                ]
                for fut in futures:
                    all_rows.extend(fut.result())
                total_wall_seconds += time.perf_counter() - start

    with open(raw_output_tsv, "w", encoding="utf-8") as raw_out:
        raw_out.write("worker\titeration\tscenario_id\tlatency_ns\n")
        for worker_id, i, sid, latency_ns in all_rows:
            raw_out.write(f"{worker_id}\t{i}\t{sid}\t{latency_ns}\n")

    all_latencies = sorted(r[3] for r in all_rows)
    mean = statistics.mean(all_latencies)
    aggregate_throughput = len(all_latencies) / total_wall_seconds
    summary = {
        "engine": "casbin-cpp",
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
        "notes": "concurrency = independent OS processes, not threads sharing one Enforcer -- "
                 "casbin::Enforcer segfaults under concurrent thread access even with one instance "
                 "per thread (confirmed empirically); peak_rss_kb is this Python orchestrator's own "
                 "RSS, not the worker processes', see semantic-mapping.md",
    }
    with open(summary_output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Casbin-CPP benchmark (concurrency={concurrency}, process-based): {len(all_latencies)} measured calls, "
          f"aggregate throughput {aggregate_throughput}/s, summary written to {summary_output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
