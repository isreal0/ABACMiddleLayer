# Semantic mapping

This document records, per canonical scenario feature, how it is represented
in each engine's native format — and where representation is impossible or
lossy. It is filled in during Step 4 as adapters are built, and updated
whenever `results/compatibility/compatibility.csv` gains a new row.

Do not leave a row's mapping implicit in adapter code only — anything that
changes an engine's effective semantics (e.g. combining-algorithm defaults,
missing-attribute handling, NotApplicable vs. Deny conflation) must be
documented here, not just handled silently.

## Status

`corpus/canonical/scenarios.json` exists (10 scenarios, UOA course-score
domain: a student's score in a specific course). Ground truth was derived
against `corpus/reference-policies/xacml3-course-score-policy.xml`, a
hand-authored XACML 3.0 policy using `permit-overrides` combining.
**Middle Layer** and **AuthzForce Core** adapters are built and verified
(10/10 correct each), sharing the exact same reference policy file.
SunXACML and Casbin-CPP adapters are still pending, so their columns in
the template below are unfilled.

Deliberately deferred to a later corpus revision (not represented by any
engine yet):
- **Missing attribute / Indeterminate.** XACML's rules for combining an
  Indeterminate rule result under `permit-overrides` are subtle and
  implementation-nuanced; rather than assert an `expected` value I haven't
  verified, this needs an empirical cross-engine comparison pass of its own
  before being added as ground truth.
- **Explicit combining-algorithm comparison** (the same conflicting
  Permit+Deny match evaluated under `permit-overrides` vs `deny-overrides`
  vs `first-applicable` to show the algorithm choice actually changes the
  outcome). The current corpus uses `permit-overrides` throughout but
  doesn't yet demonstrate the other two algorithms changing the result.
- **Datatype errors, obligations, advice** — not yet represented in any
  scenario.

## Domain and AttributeId convention (all engines, fixed in Step 2)

All canonical scenarios model **UOA student course scores** (e.g. a
student's mark in `COMPSCI101`), matching the `/UOA_CANVAS_LMS/` prefix
already hardcoded in `postgres.c` before this project started, rather than
a generic researcher/dataset example: a subject is a student/staff
account, a resource is one student's score record for one course, and the
action is the SQL verb already extracted on the Middle Layer's C side
(SELECT/INSERT/UPDATE/DELETE).

| Field | Category | AttributeId | DataType |
|---|---|---|---|
| subject.id | access-subject | `urn:oasis:names:tc:xacml:1.0:subject:subject-id` | string |
| subject.role | access-subject | `urn:uoa:canvas:subject:role` | string |
| subject.department | access-subject | `urn:uoa:canvas:subject:department` | string |
| subject.clearance | access-subject | `urn:uoa:canvas:subject:clearance` | integer |
| resource.id | resource | `urn:oasis:names:tc:xacml:1.0:resource:resource-id` | string |
| resource.owner | resource | `urn:uoa:canvas:resource:owner` | string |
| resource.department | resource | `urn:uoa:canvas:resource:department` | string |
| resource.classification | resource | `urn:uoa:canvas:resource:classification` | integer |
| action | action | `urn:oasis:names:tc:xacml:1.0:action:action-id` | string |
| environment.network | environment | `urn:uoa:canvas:environment:network` | string |
| environment.hour | environment | `urn:uoa:canvas:environment:hour` | integer |

The first four rows (core XACML AttributeIds) are unchanged from the
original single-purpose implementation. The `urn:uoa:canvas:*` rows are new
(Step 2) and are the ones every engine's adapter must reproduce under its
own naming rules (e.g. Casbin-CPP's `model.conf` request-definition fields)
for the mapping to be faithful. A missing canonical attribute is
represented by omitting it from the request entirely (not an empty string),
matching XACML's own missing-attribute semantics.

Implemented and verified in the Middle Layer as
`ABACML.Evaluate_ABAC_Decision(...)` (`abacml/src/main/java/com/yasusoft/
abacml/ABACML.java`), which returns the real decision
(Permit/Deny/NotApplicable/Indeterminate) rather than the boolean-only
`Check_ABAC_Permission` still used by the live Postgres/JNI path. See
`abacml/src/test/java/com/yasusoft/abacml/UOACanonicalDecisionTest.java`
for a 4-case worked example (permit on matching department + sufficient
clearance, deny on mismatch, NotApplicable outside the policy's action
target).

## Template (one row per canonical feature)

| Canonical feature | Middle Layer | SunXACML (XACML 2.0) | AuthzForce (XACML 3.0) | Casbin-CPP | Notes / limitations |
|---|---|---|---|---|---|
| Permit | ✅ abac-001/002/003 | pending | ✅ abac-001/002/003 (same policy) | pending | |
| Deny | ✅ abac-004/005/006/007/008/009 | pending | ✅ abac-004/005/006/007/008/009 | pending | |
| NotApplicable | ✅ abac-010 | pending | ✅ abac-010 | pending | |
| Missing attribute | deferred | deferred | deferred | deferred | See Status above — needs empirical cross-engine pass |
| Datatype error | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| Equality condition | ✅ owner==subject-id, role==literal, dept==dept | pending | ✅ same policy, same result | pending | |
| Numeric comparison | ✅ clearance>=classification, hour range | pending | ✅ same policy, same result | pending | |
| Boolean logic | ✅ AND (all rules), OR (network campus/vpn) | pending | ✅ same policy, same result | pending | |
| Set membership | ✅ action in {SELECT,UPDATE} / policy Target {SELECT,UPDATE,DELETE} | pending | ✅ same policy, same result | pending | |
| Owner-based rule | ✅ abac-002/006 | pending | ✅ abac-002/006 | pending | |
| Role-based rule | ✅ abac-001 (admin), abac-003 (lecturer) | pending | ✅ same policy, same result | pending | |
| Department-based rule | ✅ abac-003/004 | pending | ✅ same policy, same result | pending | |
| Clearance/classification comparison | ✅ abac-003/005 | pending | ✅ same policy, same result | pending | |
| Time-of-day condition | ✅ abac-008 | pending | ✅ same policy, same result | pending | |
| Network condition | ✅ abac-007 | pending | ✅ same policy, same result | pending | |
| Permit-overrides | ✅ XACML 3.0 URN (not the legacy 1.0 one — see below) | pending | ✅ same policy, same result | pending | Not yet contrasted against deny-overrides/first-applicable on the same conflict — see Status |
| Deny-overrides | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| First-applicable | not yet in corpus (used only in Step 2's throwaway test policy, not the canonical corpus) | not yet in corpus | not yet in corpus | not yet in corpus | |
| Obligations | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| Advice | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |

## Known engine-specific constraints to record here once confirmed

- **Casbin-CPP** has no native NotApplicable/obligations/advice concept —
  document the fallback representation and mark affected scenarios
  `unsupported` rather than forcing a binary Permit/Deny.
- **SunXACML** is unmaintained XACML 2.0; XACML 3.0-only constructs used by
  AuthzForce scenarios must be marked `unsupported` here, not silently
  downgraded.
- **Middle Layer** PDP is confirmed as WSO2 Balana 1.1.12, XACML 3.0 (see
  `docs/architecture.md`). Its resource granularity is still per-database in
  the live Postgres path (`Check_ABAC_Permission`); the benchmark-facing
  `Evaluate_ABAC_Decision` takes resource attributes directly and does not
  go through Postgres at all, so per-resource scenarios are representable
  for benchmarking even though the live SQL integration is coarser.
- **AuthzForce Core rejects legacy (XACML 1.0/2.0-namespaced) combining
  algorithm URNs outright** (`UnsupportedOperationException`), even under
  a XACML 3.0-schema policy. Balana accepts both forms. The shared
  reference policy therefore uses
  `urn:oasis:names:tc:xacml:3.0:rule-combining-algorithm:permit-overrides`,
  not the `:1.0:` form — anything hand-authoring a policy meant to run on
  both engines must use the 3.0-namespaced algorithm URN.
- **AuthzForce Core's PDP CLI has no batch mode** — one JVM invocation per
  request. Fine for correctness testing; something to account for when
  Step 5 separates policy-load time from per-request evaluation time, since
  JVM startup cost is otherwise conflated with evaluation cost per call.
