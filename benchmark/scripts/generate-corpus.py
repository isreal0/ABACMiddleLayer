#!/usr/bin/env python3
"""Generates per-engine native inputs from the canonical scenario corpus, at
three policy-scale tiers (Step 5: does correctness hold and how does load/
evaluation time change as the policy grows).

Usage: generate-corpus.py <canonical-scenarios-json> <output-dir> <reference-policies-dir>

Always generates all three tiers for all four engines:
  small  --    0 decoy rules (the original, hand-authored policy as-is)
  medium -- 1000 decoy rules
  large  -- 5000 decoy rules

A "decoy rule" is a rule/row whose Target/condition can never match any of
the 10 canonical scenarios (it matches a synthetic subject-id no real
scenario uses), so injecting any number of them must never change a
scenario's expected decision -- they exist purely to make the policy
larger, exercising the engine's rule-scanning/loading cost as policy size
grows, matching the master guide's "small, medium, and large policy sizes"
requirement (see docs/architecture.md for how this differs from, and
supersedes, the old policy1k/policy5k directories).

Output layout, per engine, under <output-dir>/<engine>/<tier>/:
  middle-layer/<tier>/{scenarios.tsv, policies/*.xml}
  authzforce/<tier>/{pdp.xml, Policy.xml, requests/<id>.xml}
  sunxacml/<tier>/{policy.xml, manifest.tsv, requests/<id>.xml}
  casbin-cpp/<tier>/{model.conf, policy.csv, scenarios.tsv}

scenarios.tsv columns (tab-separated, header row, empty string = attribute
absent from the scenario, e.g. a future missing-attribute scenario):
  id  subject_id  subject_role  subject_department  subject_clearance
  resource_id  resource_owner  resource_department  resource_classification
  action  env_network  env_hour  expected
"""
import json
import os
import random
import re
import shutil
import sys

SCALE_TIERS = {"small": 0, "medium": 1000, "large": 5000}

# Fixed seed so regenerating produces byte-identical decoy content on every
# VM -- required for the "same corpus commit -> same generated inputs"
# invariant to actually hold once decoys are randomized (see docs/architecture.md).
DECOY_RANDOM_SEED = 260825

DECOY_DEPARTMENTS = [
    "ComputerScience", "Engineering", "Business", "Law", "Medicine", "Psychology",
    "Chemistry", "Physics", "Mathematics", "Biology", "ArtsAndHumanities",
    "Architecture", "Nursing", "Pharmacy", "Education",
]
DECOY_ROLES = [
    "student", "lecturer", "ta", "advisor", "admin", "dean", "registrar",
    "researcher", "postdoc", "technician",
]
DECOY_NETWORKS = ["campus", "vpn", "external", "mobile-data", "guest-wifi"]
DECOY_ACTIONS = ["SELECT", "UPDATE", "DELETE"]


def _generate_decoy_specs(num_decoys):
    """Realistic-looking, structurally varied decoy rules -- three shapes
    drawn from the same value pools a real multi-department university
    policy would use (department/role/network/action names, clearance and
    hour thresholds), not a single never-matching placeholder repeated N
    times. Always Effect=Deny: under permit-overrides, a Deny-effect decoy
    can never flip an expected Permit (any matching Permit rule always
    wins), and every canonical scenario's expected Deny is already the
    policy's own default -- so these are safe to let coincidentally match
    a real scenario's attributes, which is what makes them realistic
    instead of deliberately unreachable. Reproducible via a fixed seed.
    """
    rng = random.Random(DECOY_RANDOM_SEED)
    specs = []
    shapes = ["role_network", "dept_clearance", "action_hour"]
    for i in range(num_decoys):
        shape = shapes[i % 3]
        if shape == "role_network":
            specs.append({"shape": shape, "role": rng.choice(DECOY_ROLES), "network": rng.choice(DECOY_NETWORKS)})
        elif shape == "dept_clearance":
            specs.append({"shape": shape, "department": rng.choice(DECOY_DEPARTMENTS), "clearance_threshold": rng.randint(1, 4)})
        else:
            specs.append({"shape": shape, "action": rng.choice(DECOY_ACTIONS), "hour_threshold": rng.randint(0, 23)})
    return specs


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


def _xacml3_decoy_rule_xml(i, spec):
    if spec["shape"] == "role_network":
        target = (
            '      <AnyOf>\n'
            '        <AllOf>\n'
            '          <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["role"]}</AttributeValue>\n'
            '            <AttributeDesignator AttributeId="urn:uoa:canvas:subject:role" Category="urn:oasis:names:tc:xacml:1.0:subject-category:access-subject" DataType="http://www.w3.org/2001/XMLSchema#string" MustBePresent="true"/>\n'
            '          </Match>\n'
            '        </AllOf>\n'
            '      </AnyOf>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:string-one-and-only">\n'
            '          <AttributeDesignator AttributeId="urn:uoa:canvas:environment:network" Category="urn:oasis:names:tc:xacml:3.0:attribute-category:environment" DataType="http://www.w3.org/2001/XMLSchema#string" MustBePresent="true"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["network"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    elif spec["shape"] == "dept_clearance":
        target = (
            '      <AnyOf>\n'
            '        <AllOf>\n'
            '          <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["department"]}</AttributeValue>\n'
            '            <AttributeDesignator AttributeId="urn:uoa:canvas:resource:department" Category="urn:oasis:names:tc:xacml:3.0:attribute-category:resource" DataType="http://www.w3.org/2001/XMLSchema#string" MustBePresent="true"/>\n'
            '          </Match>\n'
            '        </AllOf>\n'
            '      </AnyOf>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-less-than">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-one-and-only">\n'
            '          <AttributeDesignator AttributeId="urn:uoa:canvas:subject:clearance" Category="urn:oasis:names:tc:xacml:1.0:subject-category:access-subject" DataType="http://www.w3.org/2001/XMLSchema#integer" MustBePresent="true"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#integer">{spec["clearance_threshold"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    else:  # action_hour
        target = (
            '      <AnyOf>\n'
            '        <AllOf>\n'
            '          <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["action"]}</AttributeValue>\n'
            '            <AttributeDesignator AttributeId="urn:oasis:names:tc:xacml:1.0:action:action-id" Category="urn:oasis:names:tc:xacml:3.0:attribute-category:action" DataType="http://www.w3.org/2001/XMLSchema#string" MustBePresent="true"/>\n'
            '          </Match>\n'
            '        </AllOf>\n'
            '      </AnyOf>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-greater-than-or-equal">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-one-and-only">\n'
            '          <AttributeDesignator AttributeId="urn:uoa:canvas:environment:hour" Category="urn:oasis:names:tc:xacml:3.0:attribute-category:environment" DataType="http://www.w3.org/2001/XMLSchema#integer" MustBePresent="true"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#integer">{spec["hour_threshold"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    return (
        f'  <Rule Effect="Deny" RuleId="decoy-{i:05d}">\n'
        f'    <Target>\n{target}    </Target>\n'
        f'    <Condition>\n{condition}    </Condition>\n'
        f'  </Rule>\n'
    )


def _xacml3_decoy_rules(num_decoys):
    if num_decoys == 0:
        return ""
    specs = _generate_decoy_specs(num_decoys)
    return "".join(_xacml3_decoy_rule_xml(i, spec) for i, spec in enumerate(specs))


def _xacml2_decoy_rule_xml(i, spec):
    if spec["shape"] == "role_network":
        target = (
            '      <Subjects>\n'
            '        <Subject>\n'
            '          <SubjectMatch MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["role"]}</AttributeValue>\n'
            '            <SubjectAttributeDesignator AttributeId="urn:uoa:canvas:subject:role" DataType="http://www.w3.org/2001/XMLSchema#string"/>\n'
            '          </SubjectMatch>\n'
            '        </Subject>\n'
            '      </Subjects>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:string-one-and-only">\n'
            '          <EnvironmentAttributeDesignator AttributeId="urn:uoa:canvas:environment:network" DataType="http://www.w3.org/2001/XMLSchema#string"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["network"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    elif spec["shape"] == "dept_clearance":
        target = (
            '      <Resources>\n'
            '        <Resource>\n'
            '          <ResourceMatch MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["department"]}</AttributeValue>\n'
            '            <ResourceAttributeDesignator AttributeId="urn:uoa:canvas:resource:department" DataType="http://www.w3.org/2001/XMLSchema#string"/>\n'
            '          </ResourceMatch>\n'
            '        </Resource>\n'
            '      </Resources>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-less-than">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-one-and-only">\n'
            '          <SubjectAttributeDesignator AttributeId="urn:uoa:canvas:subject:clearance" DataType="http://www.w3.org/2001/XMLSchema#integer"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#integer">{spec["clearance_threshold"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    else:  # action_hour
        target = (
            '      <Actions>\n'
            '        <Action>\n'
            '          <ActionMatch MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">\n'
            f'            <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">{spec["action"]}</AttributeValue>\n'
            '            <ActionAttributeDesignator AttributeId="urn:oasis:names:tc:xacml:1.0:action:action-id" DataType="http://www.w3.org/2001/XMLSchema#string"/>\n'
            '          </ActionMatch>\n'
            '        </Action>\n'
            '      </Actions>\n'
        )
        condition = (
            '      <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-greater-than-or-equal">\n'
            '        <Apply FunctionId="urn:oasis:names:tc:xacml:1.0:function:integer-one-and-only">\n'
            '          <EnvironmentAttributeDesignator AttributeId="urn:uoa:canvas:environment:hour" DataType="http://www.w3.org/2001/XMLSchema#integer"/>\n'
            '        </Apply>\n'
            f'        <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#integer">{spec["hour_threshold"]}</AttributeValue>\n'
            '      </Apply>\n'
        )
    return (
        f'  <Rule RuleId="decoy-{i:05d}" Effect="Deny">\n'
        f'    <Target>\n{target}    </Target>\n'
        f'    <Condition>\n{condition}    </Condition>\n'
        f'  </Rule>\n'
    )


def _xacml2_decoy_rules(num_decoys):
    if num_decoys == 0:
        return ""
    specs = _generate_decoy_specs(num_decoys)
    return "".join(_xacml2_decoy_rule_xml(i, spec) for i, spec in enumerate(specs))


def _casbin_decoy_row(i, spec):
    if spec["shape"] == "role_network":
        sub, obj, act = f'decoy_{spec["role"]}_{i:05d}', f'decoy_net_{spec["network"]}_{i:05d}', "DECOY"
    elif spec["shape"] == "dept_clearance":
        sub, obj, act = f'decoy_clr{spec["clearance_threshold"]}_{i:05d}', f'decoy_{spec["department"]}_{i:05d}', "DECOY"
    else:
        sub, obj, act = f'decoy_hr{spec["hour_threshold"]}_{i:05d}', f'decoy_obj_{i:05d}', spec["action"]
    return f"p, {sub}, {obj}, {act}\n"


def _inject_before_closing_policy(policy_xml, decoy_rules_xml):
    if not decoy_rules_xml:
        return policy_xml
    marker = "</Policy>"
    idx = policy_xml.rindex(marker)
    return policy_xml[:idx] + decoy_rules_xml + policy_xml[idx:]


def generate_middle_layer(scenarios, output_dir, ref_policies_dir):
    ref_name = "xacml3-course-score-policy.xml"
    with open(os.path.join(ref_policies_dir, ref_name), "r", encoding="utf-8") as f:
        base_policy_xml = f.read()

    for tier, num_decoys in SCALE_TIERS.items():
        ml_dir = os.path.join(output_dir, "middle-layer", tier)
        ml_policies_dir = os.path.join(ml_dir, "policies")
        os.makedirs(ml_policies_dir, exist_ok=True)

        # Only the XACML 3.0 reference policy -- Balana loads every *.xml file
        # in its policy directory, so copying the whole ref_policies_dir
        # (which also holds the XACML 2.0 translation for SunXACML) would
        # make it try to load a policy in a namespace/schema it never needs.
        policy_xml = _inject_before_closing_policy(base_policy_xml, _xacml3_decoy_rules(num_decoys))
        with open(os.path.join(ml_policies_dir, ref_name), "w", encoding="utf-8") as f:
            f.write(policy_xml)

        write_scenarios_tsv(scenarios, os.path.join(ml_dir, "scenarios.tsv"))
        print(f"[middle-layer/{tier}] {num_decoys} decoy rules, wrote {ml_dir}")


def generate_casbin_cpp(scenarios, output_dir, ref_policies_dir):
    with open(os.path.join(ref_policies_dir, "casbin-policy.csv"), "r", encoding="utf-8") as f:
        base_policy_csv = f.read()

    for tier, num_decoys in SCALE_TIERS.items():
        cb_dir = os.path.join(output_dir, "casbin-cpp", tier)
        os.makedirs(cb_dir, exist_ok=True)

        shutil.copyfile(os.path.join(ref_policies_dir, "casbin-model.conf"), os.path.join(cb_dir, "model.conf"))

        specs = _generate_decoy_specs(num_decoys)
        decoy_rows = "".join(_casbin_decoy_row(i, spec) for i, spec in enumerate(specs))
        with open(os.path.join(cb_dir, "policy.csv"), "w", encoding="utf-8") as f:
            f.write(base_policy_csv + decoy_rows)

        write_scenarios_tsv(scenarios, os.path.join(cb_dir, "scenarios.tsv"))
        print(f"[casbin-cpp/{tier}] {num_decoys} decoy rows, wrote {cb_dir}")


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
    ref_policy_path = os.path.join(ref_policies_dir, "xacml3-course-score-policy.xml")
    with open(ref_policy_path, "r", encoding="utf-8") as f:
        base_policy_xml = f.read()
    m = re.search(r'PolicyId="([^"]+)"', base_policy_xml)
    if not m:
        raise ValueError(f"could not find PolicyId in {ref_policy_path}")
    policy_id = m.group(1)

    request_cache = {}
    for s in scenarios:
        subject = s.get("subject", {})
        resource = s.get("resource", {})
        environment = s.get("environment", {})
        request_cache[s["id"]] = build_xacml3_request(
            subject.get("id"), subject.get("role"), subject.get("department"), subject.get("clearance"),
            resource.get("id"), resource.get("owner"), resource.get("department"), resource.get("classification"),
            s.get("action"), environment.get("network"), environment.get("hour"),
        )

    for tier, num_decoys in SCALE_TIERS.items():
        af_dir = os.path.join(output_dir, "authzforce", tier)
        requests_dir = os.path.join(af_dir, "requests")
        os.makedirs(requests_dir, exist_ok=True)

        policy_xml = _inject_before_closing_policy(base_policy_xml, _xacml3_decoy_rules(num_decoys))
        with open(os.path.join(af_dir, "Policy.xml"), "w", encoding="utf-8") as f:
            f.write(policy_xml)

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

        for sid, req_xml in request_cache.items():
            with open(os.path.join(requests_dir, f'{sid}.xml'), "w", encoding="utf-8") as f:
                f.write(req_xml)

        print(f"[authzforce/{tier}] {num_decoys} decoy rules, wrote {af_dir}")


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
    ref_policy_path = os.path.join(ref_policies_dir, "xacml2-course-score-policy.xml")
    with open(ref_policy_path, "r", encoding="utf-8") as f:
        base_policy_xml = f.read()

    request_cache = {}
    for s in scenarios:
        subject = s.get("subject", {})
        resource = s.get("resource", {})
        environment = s.get("environment", {})
        request_cache[s["id"]] = build_xacml2_request(
            subject.get("id"), subject.get("role"), subject.get("department"), subject.get("clearance"),
            resource.get("id"), resource.get("owner"), resource.get("department"), resource.get("classification"),
            s.get("action"), environment.get("network"), environment.get("hour"),
        )

    for tier, num_decoys in SCALE_TIERS.items():
        sx_dir = os.path.join(output_dir, "sunxacml", tier)
        requests_dir = os.path.join(sx_dir, "requests")
        os.makedirs(requests_dir, exist_ok=True)

        policy_xml = _inject_before_closing_policy(base_policy_xml, _xacml2_decoy_rules(num_decoys))
        with open(os.path.join(sx_dir, "policy.xml"), "w", encoding="utf-8") as f:
            f.write(policy_xml)

        manifest_path = os.path.join(sx_dir, "manifest.tsv")
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
            mf.write("id\texpected\n")
            for s in scenarios:
                with open(os.path.join(requests_dir, f'{s["id"]}.xml'), "w", encoding="utf-8") as f:
                    f.write(request_cache[s["id"]])
                mf.write(f'{s["id"]}\t{s["expected"]}\n')

        print(f"[sunxacml/{tier}] {num_decoys} decoy rules, wrote {sx_dir}")


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
