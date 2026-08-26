#!/usr/bin/env python3
"""Correctness-only runner for the AuthzForce Core adapter (Step 4/5A).

Usage: run-authzforce-correctness.py <cli-jar> <generated-authzforce-dir> \
           <canonical-scenarios-json> <output-jsonl> <corpus-commit> <adapter-commit>

Invokes the AuthzForce PDP CLI once per scenario (no batch mode exists),
parses the XACML Response for the Decision, and writes one normalized JSON
line per scenario matching benchmark/schemas/result.schema.json.
"""
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

XACML3_NS = "urn:oasis:names:tc:xacml:3.0:core:schema:wd-17"


def run_one(cli_jar, pdp_xml, request_xml):
    proc = subprocess.run(
        ["java", "-jar", cli_jar, "-p", pdp_xml, request_xml],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        return None, f"cli exit {proc.returncode}: {proc.stderr.strip()[-500:]}"
    try:
        root = ET.fromstring(proc.stdout)
    except ET.ParseError as e:
        return None, f"could not parse response XML: {e}; stdout={proc.stdout[:500]!r}"
    decision_el = root.find(f".//{{{XACML3_NS}}}Decision")
    if decision_el is None or decision_el.text is None:
        return None, f"no Decision element in response: {proc.stdout[:500]!r}"
    return decision_el.text.strip(), None


def json_str(s):
    return json.dumps(s) if s is not None else "null"


def to_json_line(run_id, hostname, corpus_commit, adapter_commit, scenario_id, expected, actual, correct, error):
    return (
        "{"
        f'"run_id":{json_str(run_id)},'
        '"engine":"authzforce",'
        '"engine_version":"21.2.1-SNAPSHOT",'
        f'"hostname":{json_str(hostname)},'
        f'"corpus_commit":{json_str(corpus_commit)},'
        f'"adapter_commit":{json_str(adapter_commit)},'
        f'"scenario_id":{json_str(scenario_id)},'
        f'"expected":{json_str(expected)},'
        f'"actual":{json_str(actual)},'
        '"supported":true,'
        f'"correct":{"true" if correct else "false"},'
        '"policy_load_ns":null,"translation_ns":null,"evaluation_ns":null,"total_ns":null,'
        f'"error":{json_str(error)},'
        '"notes":null'
        "}"
    )


def main():
    if len(sys.argv) != 7:
        print("usage: run-authzforce-correctness.py <cli-jar> <generated-authzforce-dir> "
              "<canonical-scenarios-json> <output-jsonl> <corpus-commit> <adapter-commit>", file=sys.stderr)
        return 2
    cli_jar, af_dir, canonical_path, output_jsonl, corpus_commit, adapter_commit = sys.argv[1:7]

    pdp_xml = os.path.join(af_dir, "pdp.xml")
    requests_dir = os.path.join(af_dir, "requests")

    with open(canonical_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    hostname = os.uname().nodename
    run_id = f"run-{int(time.time() * 1000)}"

    total = 0
    correct = 0
    with open(output_jsonl, "w", encoding="utf-8") as out:
        for s in scenarios:
            total += 1
            sid = s["id"]
            expected = s["expected"]
            request_xml = os.path.join(requests_dir, f"{sid}.xml")
            actual, error = run_one(cli_jar, pdp_xml, request_xml)
            is_correct = actual == expected
            if is_correct:
                correct += 1
            out.write(to_json_line(run_id, hostname, corpus_commit, adapter_commit, sid, expected, actual, is_correct, error) + "\n")

    print(f"AuthzForce correctness: {correct}/{total} scenarios correct")
    return 0 if correct == total else 1


if __name__ == "__main__":
    sys.exit(main())
