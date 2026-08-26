#!/usr/bin/env bash
# Controlled benchmark execution (Step 5B). Requires the correctness gate to
# pass first (at the requested scale) and the shared benchmark manifest to
# exist; never invents timing numbers for an unimplemented path. Loops over
# every concurrency level in the manifest's concurrency_levels (comma-
# separated), writing one summary per (engine, scale, concurrency).
#
# Usage: run-benchmark.sh <engine> [scale]
#   scale: small (default), medium, large -- see scripts/generate-corpus.py
set -euo pipefail

ENGINE="${1:-}"
SCALE="${2:-small}"
VALID_ENGINES="middle-layer sunxacml authzforce casbin-cpp"
VALID_SCALES="small medium large"

if [ -z "$ENGINE" ]; then
  echo "usage: $0 <engine> [scale]   (engine: $VALID_ENGINES) (scale: $VALID_SCALES, default small)" >&2
  exit 2
fi

case " $VALID_ENGINES " in
  *" $ENGINE "*) ;;
  *) echo "error: unknown engine '$ENGINE' (expected one of: $VALID_ENGINES)" >&2; exit 2 ;;
esac

case " $VALID_SCALES " in
  *" $SCALE "*) ;;
  *) echo "error: unknown scale '$SCALE' (expected one of: $VALID_SCALES)" >&2; exit 2 ;;
esac

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$HARNESS_DIR/benchmark-manifest.conf"
CORPUS_CANONICAL="/opt/abac-research/corpus/canonical/scenarios.json"
GENERATED_DIR="/opt/abac-research/corpus/generated"
RAW_DIR="/opt/abac-research/results/raw/${ENGINE}"
NORMALIZED_DIR="/opt/abac-research/results/normalized"

if [ ! -f "$MANIFEST" ]; then
  echo "error: benchmark manifest not found at $MANIFEST." >&2
  exit 1
fi

CONCURRENCY_LEVELS="$(grep '^concurrency_levels=' "$MANIFEST" | cut -d= -f2 | tr ',' ' ')"
if [ -z "$CONCURRENCY_LEVELS" ]; then
  echo "error: concurrency_levels not set in $MANIFEST" >&2
  exit 1
fi

echo "=== correctness gate: $ENGINE @ $SCALE ==="
"$HARNESS_DIR/scripts/run-correctness.sh" "$ENGINE" "$SCALE"

mkdir -p "$RAW_DIR" "$NORMALIZED_DIR"

for CONCURRENCY in $CONCURRENCY_LEVELS; do
  RAW_TSV="$RAW_DIR/${SCALE}.c${CONCURRENCY}.tsv"
  SUMMARY_JSON="$NORMALIZED_DIR/${ENGINE}.${SCALE}.c${CONCURRENCY}.benchmark.json"

  echo "=== benchmark: $ENGINE @ $SCALE, concurrency=$CONCURRENCY ==="
  case "$ENGINE" in
    middle-layer)
      REPO_DIR="/opt/abac-research/repo"
      java -cp "$REPO_DIR/abacml/target/classes:$REPO_DIR/abacml/target/libs/*" \
        com.yasusoft.abacml.harness.MiddleLayerCorpusRunner benchmark \
        "$GENERATED_DIR/middle-layer/$SCALE/policies" \
        "$GENERATED_DIR/middle-layer/$SCALE/scenarios.tsv" \
        "$MANIFEST" "$CONCURRENCY" "$RAW_TSV" "$SUMMARY_JSON"
      ;;
    authzforce)
      ENGINE_DIR="/opt/abac-research/engine/authzforce-core"
      CLI_JAR="$(find "$ENGINE_DIR/pdp-cli/target" -maxdepth 1 -name 'authzforce-ce-core-pdp-cli-*.jar' 2>/dev/null | head -1)"
      python3 "$HARNESS_DIR/scripts/run-authzforce-benchmark.py" \
        "$CLI_JAR" "$GENERATED_DIR/authzforce/$SCALE" "$CORPUS_CANONICAL" \
        "$MANIFEST" "$CONCURRENCY" "$RAW_TSV" "$SUMMARY_JSON"
      ;;
    sunxacml)
      RUNNER_CLASSES="/opt/abac-research/engine/sunxacml-build"
      SUNXACML_JAR="/opt/abac-research/engine/sunxacml-2.0-M1.jar"
      JAXB_LIBS="/opt/abac-research/engine/jaxb-libs"
      java -cp "$RUNNER_CLASSES:$SUNXACML_JAR:$JAXB_LIBS/*" \
        SunXacmlCorpusRunner benchmark \
        "$GENERATED_DIR/sunxacml/$SCALE/policy.xml" \
        "$GENERATED_DIR/sunxacml/$SCALE/requests" \
        "$MANIFEST" "$CONCURRENCY" "$RAW_TSV" "$SUMMARY_JSON"
      ;;
    casbin-cpp)
      # Process-based, not thread-based -- casbin::Enforcer segfaults under
      # concurrent thread access even with one instance per thread (see
      # docs/semantic-mapping.md), so concurrency is independent OS
      # processes, same approach as AuthzForce.
      RUNNER_BIN="/opt/abac-research/engine/casbin-cpp/build/casbin_corpus_runner"
      python3 "$HARNESS_DIR/scripts/run-casbin-benchmark.py" \
        "$RUNNER_BIN" \
        "$GENERATED_DIR/casbin-cpp/$SCALE/model.conf" \
        "$GENERATED_DIR/casbin-cpp/$SCALE/policy.csv" \
        "$GENERATED_DIR/casbin-cpp/$SCALE/scenarios.tsv" \
        "$MANIFEST" "$CONCURRENCY" "$RAW_TSV" "$SUMMARY_JSON"
      ;;
  esac

  cat "$SUMMARY_JSON"
done
