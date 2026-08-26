#!/usr/bin/env bash
# Controlled benchmark execution (Step 5B). Requires the correctness gate to
# have passed first and a benchmark manifest to exist; never invents timing
# numbers for an unimplemented path.
set -euo pipefail

ENGINE="${1:-}"
VALID_ENGINES="middle-layer sunxacml authzforce casbin-cpp"
MANIFEST="/opt/abac-research/harness/benchmark-manifest.yaml"

if [ -z "$ENGINE" ]; then
  echo "usage: $0 <engine>   (one of: $VALID_ENGINES)" >&2
  exit 2
fi

case " $VALID_ENGINES " in
  *" $ENGINE "*) ;;
  *) echo "error: unknown engine '$ENGINE' (expected one of: $VALID_ENGINES)" >&2; exit 2 ;;
esac

if [ ! -f "$MANIFEST" ]; then
  echo "error: benchmark manifest not found at $MANIFEST (Step 4/5 not complete)." >&2
  echo "expected fields: warmup_iterations, measured_iterations, repetitions, random_seed, concurrency_levels" >&2
  exit 1
fi

echo "TODO: run correctness gate for ${ENGINE} first (scripts/run-correctness.sh ${ENGINE})"
echo "TODO: execute ${ENGINE} against manifest $MANIFEST"
echo "TODO: record per-request raw data to /opt/abac-research/results/raw/${ENGINE}/"
exit 1
