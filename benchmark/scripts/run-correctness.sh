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
REF_POLICIES_DIR="$HARNESS_DIR/corpus/reference-policies"
CORPUS_CANONICAL="/opt/abac-research/corpus/canonical/scenarios.json"
COMMIT_FILE="/opt/abac-research/versions/corpus.commit"
GENERATED_DIR="/opt/abac-research/corpus/generated"
NORMALIZED_DIR="/opt/abac-research/results/normalized"

if [ ! -f "$COMMIT_FILE" ] || [ ! -f "$CORPUS_CANONICAL" ]; then
  echo "error: canonical corpus not present at $CORPUS_CANONICAL (Step 4 not complete)." >&2
  exit 1
fi

CORPUS_COMMIT="$(cat "$COMMIT_FILE")"
ADAPTER_COMMIT="$(git -C "$HARNESS_DIR" rev-parse HEAD)"
mkdir -p "$NORMALIZED_DIR"

python3 "$HARNESS_DIR/scripts/generate-corpus.py" \
  "$CORPUS_CANONICAL" "$GENERATED_DIR" "$REF_POLICIES_DIR"

case "$ENGINE" in
  middle-layer)
    REPO_DIR="/opt/abac-research/repo"
    if [ ! -f "$REPO_DIR/abacml/target/classes/com/yasusoft/abacml/harness/MiddleLayerCorpusRunner.class" ]; then
      echo "error: MiddleLayerCorpusRunner not built. Run: (cd $REPO_DIR/abacml && mvn -q -o compile)" >&2
      exit 1
    fi
    java -cp "$REPO_DIR/abacml/target/classes:$REPO_DIR/abacml/target/libs/*" \
      com.yasusoft.abacml.harness.MiddleLayerCorpusRunner \
      "$GENERATED_DIR/middle-layer/policies" \
      "$GENERATED_DIR/middle-layer/scenarios.tsv" \
      "$NORMALIZED_DIR/middle-layer.jsonl" \
      "$CORPUS_COMMIT" "$ADAPTER_COMMIT"
    ;;
  authzforce)
    ENGINE_DIR="/opt/abac-research/engine/authzforce-core"
    CLI_JAR="$(find "$ENGINE_DIR/pdp-cli/target" -maxdepth 1 -name 'authzforce-ce-core-pdp-cli-*.jar' 2>/dev/null | head -1)"
    if [ -z "$CLI_JAR" ]; then
      echo "error: AuthzForce CLI jar not found under $ENGINE_DIR/pdp-cli/target (Step 3 build missing?)." >&2
      exit 1
    fi
    python3 "$HARNESS_DIR/scripts/run-authzforce-correctness.py" \
      "$CLI_JAR" \
      "$GENERATED_DIR/authzforce" \
      "$CORPUS_CANONICAL" \
      "$NORMALIZED_DIR/authzforce.jsonl" \
      "$CORPUS_COMMIT" "$ADAPTER_COMMIT"
    ;;
  sunxacml)
    RUNNER_CLASSES="/opt/abac-research/engine/sunxacml-build"
    SUNXACML_JAR="/opt/abac-research/engine/sunxacml-2.0-M1.jar"
    JAXB_LIBS="/opt/abac-research/engine/jaxb-libs"
    if [ ! -f "$RUNNER_CLASSES/SunXacmlCorpusRunner.class" ]; then
      echo "error: SunXacmlCorpusRunner not built. Run:" >&2
      echo "  javac -cp \"$SUNXACML_JAR:$JAXB_LIBS/*\" -d $RUNNER_CLASSES $HARNESS_DIR/harness/sunxacml/SunXacmlCorpusRunner.java" >&2
      exit 1
    fi
    java -cp "$RUNNER_CLASSES:$SUNXACML_JAR:$JAXB_LIBS/*" \
      SunXacmlCorpusRunner \
      "$GENERATED_DIR/sunxacml/policy.xml" \
      "$GENERATED_DIR/sunxacml/requests" \
      "$GENERATED_DIR/sunxacml/manifest.tsv" \
      "$NORMALIZED_DIR/sunxacml.jsonl" \
      "$CORPUS_COMMIT" "$ADAPTER_COMMIT"
    ;;
  casbin-cpp)
    RUNNER_BIN="/opt/abac-research/engine/casbin-cpp/build/casbin_corpus_runner"
    if [ ! -x "$RUNNER_BIN" ]; then
      echo "error: casbin_corpus_runner not built. Run:" >&2
      echo "  g++ -std=c++17 -O2 -I/opt/abac-research/engine/casbin-cpp/include \\" >&2
      echo "    -I/opt/abac-research/engine/casbin-cpp/build/_deps/json-src/single_include \\" >&2
      echo "    $HARNESS_DIR/harness/casbin-cpp/CasbinCorpusRunner.cpp \\" >&2
      echo "    /opt/abac-research/engine/casbin-cpp/build/casbin/libcasbin.a -lpthread -o $RUNNER_BIN" >&2
      exit 1
    fi
    "$RUNNER_BIN" \
      "$GENERATED_DIR/casbin-cpp/model.conf" \
      "$GENERATED_DIR/casbin-cpp/policy.csv" \
      "$GENERATED_DIR/casbin-cpp/scenarios.tsv" \
      "$NORMALIZED_DIR/casbin-cpp.jsonl" \
      "$CORPUS_COMMIT" "$ADAPTER_COMMIT"
    ;;
esac
