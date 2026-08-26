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

No canonical scenarios exist yet (Step 4 is not started). Step 2 did,
however, extend the Middle Layer's attribute model and lock in an
AttributeId convention (below) so the Step 4 generator has a fixed target
to emit XACML requests against — recorded here now rather than left
implicit in `abacml` source, per this document's own rule above.

## Domain and AttributeId convention (all engines, fixed in Step 2)

All canonical scenarios model **UOA Canvas LMS** records, matching the
`/UOA_CANVAS_LMS/` prefix already hardcoded in `postgres.c` before this
project started, rather than a generic researcher/dataset example: a
subject is a student/staff account, a resource is a student-record table,
and the action is the SQL verb already extracted on the Middle Layer's C
side (SELECT/INSERT/UPDATE/DELETE).

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
| Permit | | | | | |
| Deny | | | | | |
| NotApplicable | | | | | |
| Missing attribute | | | | | |
| Datatype error | | | | | |
| Equality condition | | | | | |
| Numeric comparison | | | | | |
| Boolean logic | | | | | |
| Set membership | | | | | |
| Owner-based rule | | | | | |
| Role-based rule | | | | | |
| Department-based rule | | | | | |
| Clearance/classification comparison | | | | | |
| Time-of-day condition | | | | | |
| Network condition | | | | | |
| Permit-overrides | | | | | |
| Deny-overrides | | | | | |
| First-applicable | | | | | |
| Obligations | | | | | |
| Advice | | | | | |

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
