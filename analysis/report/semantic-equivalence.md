# Semantic Equivalence

What was comparable across all four engines, and what wasn't — see
`docs/semantic-mapping.md` in the harness repo for the complete
per-feature table this summarizes, and `analysis/compatibility.csv` for
the per-scenario matrix.

## Fully comparable (all four engines represent it, three of them identically)

Permit, Deny, equality conditions, numeric comparison, boolean logic
(AND/OR), set-membership on action, owner-based/role-based/department-
based rules, clearance/classification comparison, time-of-day condition,
network condition. All three XACML engines (Middle Layer, SunXACML,
AuthzForce) agree **exactly** on every one of the 10 canonical scenarios,
using two syntactically distinct but semantically equivalent policy
translations (XACML 2.0 vs. 3.0) — a genuine cross-engine correctness
result, not three independent "it runs" checks.

## Partially comparable

**NotApplicable** (abac-010): representable by all three XACML engines;
**not representable at all by Casbin-CPP**. Confirmed from
`include/casbin/enforcer_interface.h`: every `Enforce()` variant returns
a strict `bool`. Internally Casbin does track a 3-value
`Effect::{Allow,Indeterminate,Deny}` enum during multi-policy-row
merging, but the final result always collapses Deny and Indeterminate to
`false` before returning — there is no third value ever surfaced to a
caller. The adapter marks this scenario `supported:false, correct:null`
for Casbin-CPP rather than forcing the collapse into a misleading
Permit/Deny comparison. Casbin-CPP's actual returned value for this
scenario (`Deny`) is recorded in `analysis/normalized/casbin-cpp.small.jsonl`
for transparency, but is not counted toward its correctness score.

**Combining algorithms**: `permit-overrides` is used throughout and
representable natively by all three XACML engines (with one caveat below)
and reproduced as a single OR'd matcher expression for Casbin-CPP, which
has no native combining-algorithm concept at all — there is no per-rule
structure to combine, only one fixed boolean expression per request.
`deny-overrides` and `first-applicable` are not yet exercised by any
scenario in the corpus (see `threats-to-validity.md`).

## A confirmed interoperability difference (not a corpus gap, an engine difference)

**AuthzForce Core rejects the legacy XACML 1.0-namespaced
`permit-overrides` combining-algorithm URN outright**
(`UnsupportedOperationException: legacy combining algorithms ... not
supported`), even under a XACML 3.0-schema policy. Balana (Middle Layer)
accepts both the `1.0`- and `3.0`-namespaced forms. The shared XACML 3.0
reference policy therefore uses the strict
`urn:oasis:names:tc:xacml:3.0:rule-combining-algorithm:permit-overrides`
URN — confirmed this produces identical results on Middle Layer before
and after the change. SunXACML's separate XACML 2.0 translation
correctly uses the `1.0`-namespaced form instead, since that is the
correct **native** form for XACML 2.0 (the 3.0-namespaced URNs did not
exist yet when XACML 2.0 was defined) — not a downgrade, a genuine
per-version difference.

## Not yet in the corpus at all

Missing-attribute/Indeterminate semantics, datatype errors, an explicit
demonstration that `deny-overrides`/`first-applicable` change an outcome
versus `permit-overrides` on the same conflicting rule set, obligations,
and advice. See `threats-to-validity.md` for why these were deferred
rather than guessed at.
