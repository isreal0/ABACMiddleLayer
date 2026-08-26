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
**All four adapters are built and verified.** Middle Layer and AuthzForce
Core (10/10 correct each) share the exact same XACML 3.0 reference policy
file. SunXACML (10/10 correct) uses a hand-translated XACML 2.0 form of
the same policy (`corpus/reference-policies/xacml2-course-score-policy.xml`)
— XACML 2.0 has no generic Category-attributed AttributeDesignator, so the
Target/Condition syntax is necessarily different even though the semantics
are identical. Casbin-CPP (9/9 *supported* scenarios correct) uses a
completely different representation: one fixed `[matchers]` boolean
expression (`corpus/reference-policies/casbin-model.conf`) instead of
separate Target/Rule structures, since Casbin has no per-rule combining
model at all — and it has no NotApplicable/Indeterminate concept, so
abac-010 (whose canonical answer is NotApplicable) is marked
`supported: false` for this engine rather than forced into a misleading
Permit/Deny comparison.

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
| Permit | ✅ abac-001/002/003 | ✅ abac-001/002/003 (translated policy) | ✅ abac-001/002/003 (same policy) | ✅ abac-001/002/003 (single matcher) | |
| Deny | ✅ abac-004/005/006/007/008/009 | ✅ abac-004/005/006/007/008/009 | ✅ abac-004/005/006/007/008/009 | ✅ abac-004/005/006/007/008/009 | Casbin's "Deny" is really "no matcher branch true" — indistinguishable from NotApplicable, see below |
| NotApplicable | ✅ abac-010 | ✅ abac-010 | ✅ abac-010 | ❌ **unsupported** (abac-010) | Casbin `Enforce()` is strictly boolean; abac-010 returns `Deny`, marked `supported:false` rather than compared |
| Missing attribute | deferred | deferred | deferred | deferred | See Status above — needs empirical cross-engine pass |
| Datatype error | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| Equality condition | ✅ owner==subject-id, role==literal, dept==dept | ✅ translated policy, same result | ✅ same policy, same result | ✅ `==` in Exprtk matcher | |
| Numeric comparison | ✅ clearance>=classification, hour range | ✅ translated policy, same result | ✅ same policy, same result | ✅ `>=` and `inrange()` in Exprtk matcher | |
| Boolean logic | ✅ AND (all rules), OR (network campus/vpn) | ✅ translated policy, same result | ✅ same policy, same result | ✅ `&&`/`\|\|` in Exprtk matcher | |
| Set membership | ✅ action in {SELECT,UPDATE} / policy Target {SELECT,UPDATE,DELETE} | ✅ translated policy, same result | ✅ same policy, same result | ✅ OR-chain (`x=="a" \|\| x=="b"`) — Exprtk has no native set-membership operator | |
| Owner-based rule | ✅ abac-002/006 | ✅ abac-002/006 | ✅ abac-002/006 | ✅ abac-002/006 | |
| Role-based rule | ✅ abac-001 (admin), abac-003 (lecturer) | ✅ translated policy, same result | ✅ same policy, same result | ✅ same result, one matcher clause per role | |
| Department-based rule | ✅ abac-003/004 | ✅ translated policy, same result | ✅ same policy, same result | ✅ same result | |
| Clearance/classification comparison | ✅ abac-003/005 | ✅ translated policy, same result | ✅ same policy, same result | ✅ same result | |
| Time-of-day condition | ✅ abac-008 | ✅ translated policy, same result | ✅ same policy, same result | ✅ same result via `inrange()` | |
| Network condition | ✅ abac-007 | ✅ translated policy, same result | ✅ same policy, same result | ✅ same result | |
| Permit-overrides | ✅ XACML 3.0 URN (not the legacy 1.0 one — see below) | ✅ XACML 1.0-namespaced URN (correct native form for 2.0) | ✅ same policy, same result | N/A — no per-rule combining model; all 3 conditions OR'd in one matcher expression instead | Not yet contrasted against deny-overrides/first-applicable on the same conflict — see Status |
| Deny-overrides | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| First-applicable | not yet in corpus (used only in Step 2's throwaway test policy, not the canonical corpus) | not yet in corpus | not yet in corpus | not yet in corpus | |
| Obligations | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |
| Advice | not yet in corpus | not yet in corpus | not yet in corpus | not yet in corpus | |

All four engines now agree on every scenario each can represent: three
XACML engines agree exactly on all 10 (using two distinct, semantically-
equivalent 2.0/3.0 policy translations), and Casbin-CPP agrees on all 9 of
the 10 it can represent at all — a genuine cross-engine correctness
result, not just four independent "it runs" checks.

## Known engine-specific constraints to record here once confirmed

- **Casbin-CPP** has no native NotApplicable/obligations/advice concept —
  confirmed from `include/casbin/enforcer_interface.h`: every `Enforce*`
  variant returns plain `bool`. Internally it does track a 3-value
  `Effect::{Allow,Indeterminate,Deny}` enum during multi-policy-row
  merging, but the final result always collapses Deny and Indeterminate to
  `false` before returning. Our adapter marks any scenario whose canonical
  `expected` is `NotApplicable` as `supported:false, correct:null` rather
  than forcing that collapse into a fake pass/fail. It also has **no
  per-rule Target/Rule/combining-algorithm structure at all** — Casbin's
  model is one fixed `[matchers]` boolean expression evaluated against a
  request, so instead of a translated Policy/Rule tree (as for the three
  XACML engines) we wrote the equivalent logic as a single OR-of-ANDs
  expression in `corpus/reference-policies/casbin-model.conf`. Its
  expression evaluator is a genuinely embedded Exprtk instance (supports
  `==`, `>=`, `<=`, `&&`, `||`, `inrange()`, and dotted attribute access
  into nested JSON objects) but has **no native set-membership operator**
  — `action in {SELECT, UPDATE}`-style conditions become explicit
  `(x=="SELECT" || x=="UPDATE")` OR-chains instead.
- **SunXACML** is unmaintained XACML 2.0; XACML 3.0-only constructs used by
  AuthzForce scenarios must be marked `unsupported` here, not silently
  downgraded. It also has a real runtime gap on modern JDKs: the pinned
  2010-era jar's request/response marshalling is JAXB-based
  (`javax.xml.bind`), which the JDK shipped built-in through Java 8 but
  removed entirely from Java 9 onward. On the installed OpenJDK 11, the PDP
  fails every single request with `Indeterminate` / `NoClassDefFoundError:
  javax/xml/bind/JAXBException` unless the JAXB runtime is put back on the
  classpath explicitly — resolved by adding
  `org.glassfish.jaxb:jaxb-runtime:2.3.1` (and its transitive dependencies)
  from `/opt/abac-research/engine/jaxb-libs/`. Anyone re-running this
  engine's tests from a clean classpath will hit the exact same failure if
  they omit those jars.
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
