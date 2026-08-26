# ABAC Middle Layer vs. Three Baselines — Analysis Index

Snapshot as of corpus/adapter commit `47b4300c30288c9ec53f621fdc5bf5f2ed0c793a`
(2026-08-27). This directory is a point-in-time copy of results collected
across all four VMs, aggregated here without deleting the server-side
originals, per the master guide's Step 6 instruction.

## Reports

1. [report/environment.md](report/environment.md) — server and dependency inventory
2. [report/methodology.md](report/methodology.md) — corpus, policy-scale tiers, benchmark protocol, aggregation
3. [report/semantic-equivalence.md](report/semantic-equivalence.md) — what was and wasn't comparable across engines
4. [report/correctness.md](report/correctness.md) — decision agreement and the one representational gap
5. [report/performance.md](report/performance.md) — latency, throughput, memory, concurrency
6. [report/threats-to-validity.md](report/threats-to-validity.md) — every known limitation of this snapshot, stated plainly

## Data this all traces back to

- `inventory.csv` — Step 0 hardware/OS inventory
- `versions/<hostname>/` — captured environment, checksums, engine commits, per VM
- `compatibility.csv` — per-scenario × per-engine decision matrix
- `raw/<engine>/` — per-request latency TSVs, every scale, every concurrency level
- `normalized/` — correctness JSONL + benchmark summary JSON, every scale, every concurrency level
- `MANIFEST.sha256` — SHA-256 of the canonical corpus, reference policies, and every file in this directory

## Reproducing the tables

`scripts/regenerate-tables.py` reads only the files listed above (stdlib
Python, no engine runtime needed) and reprints every table in
`report/correctness.md` and `report/performance.md`. Run it and diff
against those files to confirm nothing here was hand-typed independently
of the data:

```bash
python3 scripts/regenerate-tables.py .
```

## Reproducing the underlying data itself

See the harness repository's own `benchmark/README.md` and
`benchmark/scripts/run-correctness.sh` / `run-benchmark.sh` for how to
regenerate `raw/` and `normalized/` from scratch against a (possibly
newer) corpus commit — that will produce a *new* snapshot, not overwrite
this one.
