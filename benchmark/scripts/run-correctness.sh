#!/usr/bin/env bash
# Correctness-only execution (Step 5A). Refuses to run until the canonical
# corpus and the requested engine's adapter actually exist — never fabricates
# a pass for an unimplemented component.
set -euo pipefail

ENGINE="${1:-}"
VALID_ENGINES="middle-layer sunxacml authzforce casbin-cpp"

if [ -z "$ENGINE" ]; then
  echo "usage: $0 <engine>   (one of: $VALID_ENGINES)" >&2
  exit 2
fi

case " $VALID_ENGINES " in
  *" $ENGINE "*) ;;
  *) echo "error: unknown engine '$ENGINE' (expected one of: $VALID_ENGINES)" >&2; exit 2 ;;
esac

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORPUS_CANONICAL="/opt/abac-research/corpus/canonical/scenarios.json"
COMMIT_FILE="/opt/abac-research/versions/corpus.commit"
GENERATED_DIR="/opt/abac-research/corpus/generated"
NORMALIZED_DIR="/opt/abac-research/results/normalized"

if [ ! -f "$COMMIT_FILE" ] || [ ! -f "$CORPUS_CANONICAL" ]; then
  echo "error: canonical corpus not present at $CORPUS_CANONICAL (Step 4 not complete)." >&2
  exit 1
fi

CORPUS_COMMIT="$(cat "$COMMIT_FILE")"
mkdir -p "$NORMALIZED_DIR"

case "$ENGINE" in
  middle-layer)
    REPO_DIR="/opt/abac-research/repo"
    if [ ! -f "$REPO_DIR/abacml/target/classes/com/yasusoft/abacml/harness/MiddleLayerCorpusRunner.class" ]; then
      echo "error: MiddleLayerCorpusRunner not built. Run: (cd $REPO_DIR/abacml && mvn -q -o compile)" >&2
      exit 1
    fi
    python3 "$HARNESS_DIR/scripts/generate-corpus.py" \
      "$CORPUS_CANONICAL" "$GENERATED_DIR" "$REPO_DIR/benchmark/corpus/reference-policies"
    ADAPTER_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
    java -cp "$REPO_DIR/abacml/target/classes:$REPO_DIR/abacml/target/libs/*" \
      com.yasusoft.abacml.harness.MiddleLayerCorpusRunner \
      "$GENERATED_DIR/middle-layer/policies" \
      "$GENERATED_DIR/middle-layer/scenarios.tsv" \
      "$NORMALIZED_DIR/middle-layer.jsonl" \
      "$CORPUS_COMMIT" "$ADAPTER_COMMIT"
    ;;
  sunxacml|authzforce|casbin-cpp)
    echo "error: no adapter implemented yet for '$ENGINE' (Step 4 in progress — only middle-layer is done so far)." >&2
    exit 1
    ;;
esac
