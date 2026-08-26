# Correctness

## Headline result

**12/12 engine×scale combinations pass.** Four engines, three policy
scales each (small/medium/large), all evaluated against the same 10
canonical scenarios per `analysis/compatibility.csv`:

| Engine | Scenarios correct | Scenarios supported | Holds at small | Holds at medium | Holds at large |
|---|---|---|---|---|---|
| Middle Layer | 10/10 | 10/10 | yes | yes | yes |
| SunXACML | 10/10 | 10/10 | yes | yes | yes |
| AuthzForce Core | 10/10 | 10/10 | yes | yes | yes |
| Casbin-CPP | 9/9 | 9/10 | yes | yes | yes |

Source records: `analysis/normalized/<engine>.jsonl` (original single-scale
pass) and `analysis/normalized/<engine>.{small,medium,large}.jsonl`
(per-scale). Decoy rules injected for the medium/large tiers never change
a scenario's expected decision (verified, not assumed) — see
`methodology.md` for why that's true by construction
(`Effect="Deny"` decoys under `permit-overrides`).

## The one gap

Casbin-CPP cannot represent **abac-010** (NotApplicable) at all — see
`semantic-equivalence.md`. This is recorded as `supported:false,
correct:null`, not as a failure.

## Bugs found and fixed during adapter development

Both were caught by building real adapters and running them, not
inferred from documentation:

1. **AuthzForce rejects the legacy XACML 1.0-namespaced
   `permit-overrides` URN.** `UnsupportedOperationException` at PDP
   configuration time. Fixed by using the XACML 3.0-namespaced URN in the
   shared reference policy; re-verified Middle Layer's 10/10 was
   unaffected by the change before rolling it out to AuthzForce.

2. **Casbin-CPP's `Enforcer::Enforce()` is not thread-safe**, discovered
   during Step 5B concurrency testing (see `performance.md`): segfaults
   at concurrency ≥ 2 with one shared instance, and *still* segfaults at
   concurrency ≥ 2 with one independently-constructed instance per
   thread — meaning the fault is global/static state inside the library
   (most likely the vendored Exprtk expression engine), not fixable from
   the adapter side. Concurrency for this engine is measured via
   independent OS processes instead; correctness itself (single-threaded)
   was never affected.

## What "correct" means here

A result counts as correct only if the engine's actual decision string
(`Permit`/`Deny`/`NotApplicable`/`Indeterminate`) exactly matches the
canonical scenario's `expected` field — normalized/result.schema.json's
`correct` field is computed this way in every adapter, not asserted by
hand. `supported:false` scenarios are excluded from the correctness
denominator rather than counted as either a pass or a fail.
