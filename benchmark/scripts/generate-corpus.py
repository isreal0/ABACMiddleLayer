#!/usr/bin/env python3
"""Generates per-engine native inputs from the canonical scenario corpus.

Usage: generate-corpus.py <canonical-scenarios-json> <output-dir> <reference-policies-dir>

Writes, for the middle-layer target (the only one implemented so far --
sunxacml/authzforce/casbin-cpp are Step 4's next increment, see
benchmark/README.md status):

  <output-dir>/middle-layer/scenarios.tsv       -- one row per scenario
  <output-dir>/middle-layer/policies/*.xml      -- copy of the shared XACML
                                                    3.0 reference policy set

scenarios.tsv columns (tab-separated, header row, empty string = attribute
absent from the scenario, e.g. a future missing-attribute scenario):
  id  subject_id  subject_role  subject_department  subject_clearance
  resource_id  resource_owner  resource_department  resource_classification
  action  env_network  env_hour  expected
"""
import json
import os
import shutil
import sys


def field(d, key):
    v = d.get(key)
    return "" if v is None else str(v)


def main():
    if len(sys.argv) != 4:
        print("usage: generate-corpus.py <canonical-scenarios-json> <output-dir> <reference-policies-dir>", file=sys.stderr)
        return 2
    canonical_path, output_dir, ref_policies_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(canonical_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    ml_dir = os.path.join(output_dir, "middle-layer")
    ml_policies_dir = os.path.join(ml_dir, "policies")
    os.makedirs(ml_policies_dir, exist_ok=True)

    for name in os.listdir(ref_policies_dir):
        if name.endswith(".xml"):
            shutil.copyfile(os.path.join(ref_policies_dir, name), os.path.join(ml_policies_dir, name))

    columns = [
        "id", "subject_id", "subject_role", "subject_department", "subject_clearance",
        "resource_id", "resource_owner", "resource_department", "resource_classification",
        "action", "env_network", "env_hour", "expected",
    ]

    tsv_path = os.path.join(ml_dir, "scenarios.tsv")
    with open(tsv_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(columns) + "\n")
        for s in scenarios:
            subject = s.get("subject", {})
            resource = s.get("resource", {})
            environment = s.get("environment", {})
            row = [
                field(s, "id"),
                field(subject, "id"),
                field(subject, "role"),
                field(subject, "department"),
                field(subject, "clearance"),
                field(resource, "id"),
                field(resource, "owner"),
                field(resource, "department"),
                field(resource, "classification"),
                field(s, "action"),
                field(environment, "network"),
                field(environment, "hour"),
                field(s, "expected"),
            ]
            if any("\t" in c or "\n" in c for c in row):
                raise ValueError(f"scenario {s.get('id')} has a tab/newline in a field, TSV would be corrupted")
            f.write("\t".join(row) + "\n")

    print(f"wrote {len(scenarios)} scenarios to {tsv_path}")
    print(f"copied reference policies into {ml_policies_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
