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

CORPUS_DIR="/opt/abac-research/corpus/canonical"
COMMIT_FILE="/opt/abac-research/versions/corpus.commit"
ADAPTER_DIR="/opt/abac-research/harness/adapters/${ENGINE}"

if [ ! -f "$COMMIT_FILE" ] || [ -z "$(ls -A "$CORPUS_DIR" 2>/dev/null || true)" ]; then
  echo "error: canonical corpus not present at $CORPUS_DIR (Step 4 not complete)." >&2
  exit 1
fi

if [ ! -d "$ADAPTER_DIR" ]; then
  echo "error: no adapter found at $ADAPTER_DIR for engine '$ENGINE' (Step 4 not complete)." >&2
  exit 1
fi

echo "TODO: invoke ${ENGINE} adapter against $CORPUS_DIR (commit $(cat "$COMMIT_FILE"))"
echo "TODO: write normalized results to /opt/abac-research/results/normalized/"
exit 1
