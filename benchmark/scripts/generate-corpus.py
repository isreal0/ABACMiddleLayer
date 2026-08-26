#!/usr/bin/env python3
"""Generates per-engine native inputs from the canonical scenario corpus.

Usage: generate-corpus.py <canonical-scenarios-json> <output-dir> <reference-policies-dir>

Writes, for each implemented target (sunxacml/casbin-cpp are Step 4's next
increment, see benchmark/README.md status):

  <output-dir>/middle-layer/scenarios.tsv       -- one row per scenario
  <output-dir>/middle-layer/policies/*.xml      -- copy of the shared XACML
                                                    3.0 reference policy set

  <output-dir>/authzforce/pdp.xml               -- AuthzForce PDP config
  <output-dir>/authzforce/Policy.xml            -- copy of the reference policy
  <output-dir>/authzforce/requests/<id>.xml     -- one XACML 3.0 Request per
                                                    scenario (same AttributeId
                                                    convention as the Middle
                                                    Layer's own request builder)

scenarios.tsv columns (tab-separated, header row, empty string = attribute
absent from the scenario, e.g. a future missing-attribute scenario):
  id  subject_id  subject_role  subject_department  subject_clearance
  resource_id  resource_owner  resource_department  resource_classification
  action  env_network  env_hour  expected
"""
import json
import os
import re
import shutil
import sys


def field(d, key):
    v = d.get(key)
    return "" if v is None else str(v)


def write_scenarios_tsv(scenarios, tsv_path):
    columns = [
        "id", "subject_id", "subject_role", "subject_department", "subject_clearance",
        "resource_id", "resource_owner", "resource_department", "resource_classification",
        "action", "env_network", "env_hour", "expected",
    ]
    with open(tsv_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(columns) + "\n")
        for s in scenarios:
            subject = s.get("subject", {})
            resource = s.get("resource", {})
            environment = s.get("environment", {})
            row = [
                field(s, "id"), field(subject, "id"), field(subject, "role"),
                field(subject, "department"), field(subject, "clearance"),
                field(resource, "id"), field(resource, "owner"),
                field(resource, "department"), field(resource, "classification"),
                field(s, "action"), field(environment, "network"), field(environment, "hour"),
                field(s, "expected"),
            ]
            if any("\t" in c or "\n" in c for c in row):
                raise ValueError(f"scenario {s.get('id')} has a tab/newline in a field, TSV would be corrupted")
            f.write("\t".join(row) + "\n")
    print(f"wrote {len(scenarios)} scenarios to {tsv_path}")


def generate_middle_layer(scenarios, output_dir, ref_policies_dir):
    ml_dir = os.path.join(output_dir, "middle-layer")
    ml_policies_dir = os.path.join(ml_dir, "policies")
    os.makedirs(ml_policies_dir, exist_ok=True)

    # Only the XACML 3.0 reference policy -- Balana loads every *.xml file in
    # its policy directory, so copying the whole ref_policies_dir (which also
    # holds the XACML 2.0 translation for SunXACML) would make it try to load
    # a policy in a namespace/schema it never needs to see.
    ref_name = "xacml3-course-score-policy.xml"
    shutil.copyfile(os.path.join(ref_policies_dir, ref_name), os.path.join(ml_policies_dir, ref_name))

    write_scenarios_tsv(scenarios, os.path.join(ml_dir, "scenarios.tsv"))
    print(f"copied reference policies into {ml_policies_dir}")


def generate_casbin_cpp(scenarios, output_dir, ref_policies_dir):
    cb_dir = os.path.join(output_dir, "casbin-cpp")
    os.makedirs(cb_dir, exist_ok=True)

    shutil.copyfile(os.path.join(ref_policies_dir, "casbin-model.conf"), os.path.join(cb_dir, "model.conf"))
    shutil.copyfile(os.path.join(ref_policies_dir, "casbin-policy.csv"), os.path.join(cb_dir, "policy.csv"))

    write_scenarios_tsv(scenarios, os.path.join(cb_dir, "scenarios.tsv"))
    print(f"copied model.conf + policy.csv to {cb_dir}")


def _xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


def _string_attr(attribute_id, value):
    if value is None:
        return ""
    return (f'    <Attribute IncludeInResult="false" AttributeId="{attribute_id}">\n'
            f'      <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(str(value))}</AttributeValue>\n'
            f'    </Attribute>\n')


def _integer_attr(attribute_id, value):
    if value is None:
        return ""
    return (f'    <Attribute IncludeInResult="false" AttributeId="{attribute_id}">\n'
            f'      <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#integer">{value}</AttributeValue>\n'
            f'    </Attribute>\n')


def build_xacml3_request(subject_id, subject_role, subject_department, subject_clearance,
                          resource_id, resource_owner, resource_department, resource_classification,
                          action, env_network, env_hour):
    """Same AttributeId convention as ABACML.createCanonicalXACMLRequest (Java) --
    see benchmark/docs/semantic-mapping.md. Kept in sync by hand; if you change
    one, change the other and re-verify both adapters."""
    subject_attrs = (
        _string_attr("urn:oasis:names:tc:xacml:1.0:subject:subject-id", subject_id)
        + _string_attr("urn:uoa:canvas:subject:role", subject_role)
        + _string_attr("urn:uoa:canvas:subject:department", subject_department)
        + _integer_attr("urn:uoa:canvas:subject:clearance", subject_clearance)
    )
    resource_attrs = (
        _string_attr("urn:oasis:names:tc:xacml:1.0:resource:resource-id", resource_id)
        + _string_attr("urn:uoa:canvas:resource:owner", resource_owner)
        + _string_attr("urn:uoa:canvas:resource:department", resource_department)
        + _integer_attr("urn:uoa:canvas:resource:classification", resource_classification)
    )
    action_attrs = _string_attr("urn:oasis:names:tc:xacml:1.0:action:action-id", action)
    env_attrs = (
        _string_attr("urn:uoa:canvas:environment:network", env_network)
        + _integer_attr("urn:uoa:canvas:environment:hour", env_hour)
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Request xmlns="urn:oasis:names:tc:xacml:3.0:core:schema:wd-17" CombinedDecision="false" ReturnPolicyIdList="false">
  <Attributes Category="urn:oasis:names:tc:xacml:1.0:subject-category:access-subject">
{subject_attrs}  </Attributes>
  <Attributes Category="urn:oasis:names:tc:xacml:3.0:attribute-category:resource">
{resource_attrs}  </Attributes>
  <Attributes Category="urn:oasis:names:tc:xacml:3.0:attribute-category:action">
{action_attrs}  </Attributes>
  <Attributes Category="urn:oasis:names:tc:xacml:3.0:attribute-category:environment">
{env_attrs}  </Attributes>
</Request>
'''


def generate_authzforce(scenarios, output_dir, ref_policies_dir):
    af_dir = os.path.join(output_dir, "authzforce")
    requests_dir = os.path.join(af_dir, "requests")
    os.makedirs(requests_dir, exist_ok=True)

    ref_policy_path = os.path.join(ref_policies_dir, "xacml3-course-score-policy.xml")
    policy_dest = os.path.join(af_dir, "Policy.xml")
    shutil.copyfile(ref_policy_path, policy_dest)

    with open(ref_policy_path, "r", encoding="utf-8") as f:
        policy_xml = f.read()
    m = re.search(r'PolicyId="([^"]+)"', policy_xml)
    if not m:
        raise ValueError(f"could not find PolicyId in {ref_policy_path}")
    policy_id = m.group(1)

    pdp_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<pdp xmlns="http://authzforce.github.io/core/xmlns/pdp/8"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     version="8.0">
   <policyProvider id="rootPolicyProvider" xsi:type="StaticPolicyProvider">
      <policyLocation>${{PARENT_DIR}}/Policy.xml</policyLocation>
   </policyProvider>
   <rootPolicyRef>{policy_id}</rootPolicyRef>
</pdp>
'''
    with open(os.path.join(af_dir, "pdp.xml"), "w", encoding="utf-8") as f:
        f.write(pdp_xml)

    for s in scenarios:
        subject = s.get("subject", {})
        resource = s.get("resource", {})
        environment = s.get("environment", {})
        req_xml = build_xacml3_request(
            subject.get("id"), subject.get("role"), subject.get("department"), subject.get("clearance"),
            resource.get("id"), resource.get("owner"), resource.get("department"), resource.get("classification"),
            s.get("action"), environment.get("network"), environment.get("hour"),
        )
        with open(os.path.join(requests_dir, f'{s["id"]}.xml'), "w", encoding="utf-8") as f:
            f.write(req_xml)

    print(f"wrote pdp.xml + Policy.xml to {af_dir}")
    print(f"wrote {len(scenarios)} request files to {requests_dir}")


def _sunxacml_string_attr(attribute_id, value):
    if value is None:
        return ""
    return (f'    <Attribute AttributeId="{attribute_id}" DataType="http://www.w3.org/2001/XMLSchema#string">\n'
            f'      <AttributeValue>{_xml_escape(str(value))}</AttributeValue>\n'
            f'    </Attribute>\n')


def _sunxacml_integer_attr(attribute_id, value):
    if value is None:
        return ""
    return (f'    <Attribute AttributeId="{attribute_id}" DataType="http://www.w3.org/2001/XMLSchema#integer">\n'
            f'      <AttributeValue>{value}</AttributeValue>\n'
            f'    </Attribute>\n')


def build_xacml2_request(subject_id, subject_role, subject_department, subject_clearance,
                          resource_id, resource_owner, resource_department, resource_classification,
                          action, env_network, env_hour):
    """XACML 2.0 request format (Subject/Resource/Action/Environment elements,
    not XACML 3.0's Category-attributed Attributes) -- required by SunXACML.
    Same AttributeId convention as build_xacml3_request; see
    benchmark/docs/semantic-mapping.md."""
    subject_attrs = (
        _sunxacml_string_attr("urn:oasis:names:tc:xacml:1.0:subject:subject-id", subject_id)
        + _sunxacml_string_attr("urn:uoa:canvas:subject:role", subject_role)
        + _sunxacml_string_attr("urn:uoa:canvas:subject:department", subject_department)
        + _sunxacml_integer_attr("urn:uoa:canvas:subject:clearance", subject_clearance)
    )
    resource_attrs = (
        _sunxacml_string_attr("urn:oasis:names:tc:xacml:1.0:resource:resource-id", resource_id)
        + _sunxacml_string_attr("urn:uoa:canvas:resource:owner", resource_owner)
        + _sunxacml_string_attr("urn:uoa:canvas:resource:department", resource_department)
        + _sunxacml_integer_attr("urn:uoa:canvas:resource:classification", resource_classification)
    )
    action_attrs = _sunxacml_string_attr("urn:oasis:names:tc:xacml:1.0:action:action-id", action)
    env_attrs = (
        _sunxacml_string_attr("urn:uoa:canvas:environment:network", env_network)
        + _sunxacml_integer_attr("urn:uoa:canvas:environment:hour", env_hour)
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Request xmlns="urn:oasis:names:tc:xacml:2.0:context:schema:os">
  <Subject>
{subject_attrs}  </Subject>
  <Resource>
{resource_attrs}  </Resource>
  <Action>
{action_attrs}  </Action>
  <Environment>
{env_attrs}  </Environment>
</Request>
'''


def generate_sunxacml(scenarios, output_dir, ref_policies_dir):
    sx_dir = os.path.join(output_dir, "sunxacml")
    requests_dir = os.path.join(sx_dir, "requests")
    os.makedirs(requests_dir, exist_ok=True)

    ref_policy_path = os.path.join(ref_policies_dir, "xacml2-course-score-policy.xml")
    shutil.copyfile(ref_policy_path, os.path.join(sx_dir, "policy.xml"))

    manifest_path = os.path.join(sx_dir, "manifest.tsv")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
        mf.write("id\texpected\n")
        for s in scenarios:
            subject = s.get("subject", {})
            resource = s.get("resource", {})
            environment = s.get("environment", {})
            req_xml = build_xacml2_request(
                subject.get("id"), subject.get("role"), subject.get("department"), subject.get("clearance"),
                resource.get("id"), resource.get("owner"), resource.get("department"), resource.get("classification"),
                s.get("action"), environment.get("network"), environment.get("hour"),
            )
            with open(os.path.join(requests_dir, f'{s["id"]}.xml'), "w", encoding="utf-8") as f:
                f.write(req_xml)
            mf.write(f'{s["id"]}\t{s["expected"]}\n')

    print(f"wrote policy.xml + manifest.tsv to {sx_dir}")
    print(f"wrote {len(scenarios)} request files to {requests_dir}")


def main():
    if len(sys.argv) != 4:
        print("usage: generate-corpus.py <canonical-scenarios-json> <output-dir> <reference-policies-dir>", file=sys.stderr)
        return 2
    canonical_path, output_dir, ref_policies_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(canonical_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    generate_middle_layer(scenarios, output_dir, ref_policies_dir)
    generate_authzforce(scenarios, output_dir, ref_policies_dir)
    generate_sunxacml(scenarios, output_dir, ref_policies_dir)
    generate_casbin_cpp(scenarios, output_dir, ref_policies_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
