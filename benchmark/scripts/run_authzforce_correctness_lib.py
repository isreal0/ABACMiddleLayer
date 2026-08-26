"""Shared AuthzForce CLI invocation helper, used by both
run-authzforce-correctness.py (Step 4/5A) and run-authzforce-benchmark.py
(Step 5B). Not a hyphenated filename so it can be imported normally.
"""
import subprocess
import time
import xml.etree.ElementTree as ET

XACML3_NS = "urn:oasis:names:tc:xacml:3.0:core:schema:wd-17"


def run_one(cli_jar, pdp_xml, request_xml):
    # The CLI has no batch mode -- every call is a fresh JVM process that
    # re-parses pdp.xml/Policy.xml from scratch, so JVM startup + policy
    # load + evaluation are inseparable here. total_ns below is the whole
    # subprocess wall time, not a clean per-request evaluation time; see
    # benchmark/docs/semantic-mapping.md for why policy_load_ns/
    # evaluation_ns are left null for this engine specifically.
    start = time.perf_counter_ns()
    proc = subprocess.run(
        ["java", "-jar", cli_jar, "-p", pdp_xml, request_xml],
        capture_output=True, text=True, timeout=60,
    )
    total_ns = time.perf_counter_ns() - start
    if proc.returncode != 0:
        return None, f"cli exit {proc.returncode}: {proc.stderr.strip()[-500:]}", total_ns
    try:
        root = ET.fromstring(proc.stdout)
    except ET.ParseError as e:
        return None, f"could not parse response XML: {e}; stdout={proc.stdout[:500]!r}", total_ns
    decision_el = root.find(f".//{{{XACML3_NS}}}Decision")
    if decision_el is None or decision_el.text is None:
        return None, f"no Decision element in response: {proc.stdout[:500]!r}", total_ns
    return decision_el.text.strip(), None, total_ns
