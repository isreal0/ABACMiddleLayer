#!/usr/bin/env python3
"""Regenerates every table in report/performance.md and report/correctness.md
directly from the raw/normalized data in this analysis/ directory -- proof
that those tables are derived, not hand-typed. Uses only the Python
standard library (no engine runtime needed to re-run this).

Usage: python3 scripts/regenerate-tables.py [analysis-dir]
  (defaults to the parent of this script's own directory)
"""
import json
import os
import sys

ENGINES = ["middle-layer", "sunxacml", "authzforce", "casbin-cpp"]
SCALES = ["small", "medium", "large"]
CONCURRENCY_LEVELS = [1, 2, 4, 8]


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fmt_ns(ns):
    if ns is None:
        return "n/a"
    if ns >= 1e9:
        return f"{ns / 1e9:.2f} s"
    if ns >= 1e6:
        return f"{ns / 1e6:.1f} ms"
    return f"{ns / 1e3:.2f} us"


def regenerate_correctness_table(analysis_dir):
    print("## Correctness (regenerated from analysis/normalized/<engine>.<scale>.jsonl)\n")
    print("| Engine | Scale | Correct | Supported | Total |")
    print("|---|---|---|---|---|")
    for engine in ENGINES:
        for scale in SCALES:
            path = os.path.join(analysis_dir, "normalized", f"{engine}.{scale}.jsonl")
            rows = load_jsonl(path)
            if not rows:
                continue
            total = len(rows)
            supported = sum(1 for r in rows if r.get("supported"))
            correct = sum(1 for r in rows if r.get("correct") is True)
            print(f"| {engine} | {scale} | {correct}/{supported} | {supported}/{total} | {total} |")
    print()


def regenerate_performance_table(analysis_dir):
    print("## Single-threaded latency/throughput/RSS across policy scale "
          "(regenerated from analysis/normalized/<engine>.<scale>.benchmark.json)\n")
    print("| Engine | Scale | Median | p95 | p99 | Throughput/s | Peak RSS (KB) |")
    print("|---|---|---|---|---|---|---|")
    for engine in ENGINES:
        for scale in SCALES:
            path = os.path.join(analysis_dir, "normalized", f"{engine}.{scale}.benchmark.json")
            d = load_json(path)
            if not d:
                continue
            lat = d["latency_ns"]
            throughput = d.get("aggregate_throughput_per_sec", d.get("throughput_per_sec"))
            print(f"| {engine} | {scale} | {fmt_ns(lat['median'])} | {fmt_ns(lat['p95'])} | "
                  f"{fmt_ns(lat['p99'])} | {throughput:.1f} | {d.get('peak_rss_kb', 'n/a')} |")
    print()


def regenerate_concurrency_table(analysis_dir):
    print("## Concurrency, small scale only (regenerated from "
          "analysis/normalized/<engine>.small.c<N>.benchmark.json)\n")
    header = "| Engine | " + " | ".join(f"c={c}" for c in CONCURRENCY_LEVELS) + " |"
    print(header)
    print("|---|" + "---|" * len(CONCURRENCY_LEVELS))
    for engine in ENGINES:
        cells = []
        for c in CONCURRENCY_LEVELS:
            path = os.path.join(analysis_dir, "normalized", f"{engine}.small.c{c}.benchmark.json")
            d = load_json(path)
            if not d:
                cells.append("n/a")
                continue
            cells.append(f"{d['aggregate_throughput_per_sec']:.1f}")
        print(f"| {engine} | " + " | ".join(cells) + " |")
    print()


def main():
    analysis_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..")
    analysis_dir = os.path.abspath(analysis_dir)
    print(f"<!-- regenerated from {analysis_dir} -->\n")
    regenerate_correctness_table(analysis_dir)
    regenerate_performance_table(analysis_dir)
    regenerate_concurrency_table(analysis_dir)


if __name__ == "__main__":
    main()
