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

Not started — no canonical scenarios exist yet (Step 4 is not started).

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
- **Middle Layer** PDP choice is still open (see `docs/architecture.md`) and
  will determine which XACML version/features it can represent.
