# Modelo maturity profile

This M0–M4 scale is **organisation-defined**, not an official NIST maturity scale.

| Level | Outcome and evidence needed |
|---|---|
| M0 Provider catalogue | Provider observations and availability only |
| M1 Governed component registry | ModelRelease, Offering, Evidence, Conditions and controlled acceptance |
| M2 Linked AI-system inventory | External applications and AI uses reference Modelo Offerings |
| M3 Reconciled operating inventory | Declared and observed use compared; gaps and stale records measured |
| M4 Continuous assurance | Provider, route, evidence, use and incident changes trigger proportionate review |

## Current versus target

Assessment scope: repository base `3ebcfdb` and issue #70 implementation, not an
organisational operating assessment. The product targets **M1**.

| Evidence layer | Defensible status |
|---|---|
| Target contract | M1 governed component registry; postmerge publication/receipts specified |
| Locally implemented | Validator, deterministic candidate/final/demo builders, premerge adapter and synthetic tests; identity profile strengthens these |
| Remotely proven | Public synthetic demonstration and merged development history; not proof of all organisational controls |
| Production operating | No assessment period, no production catalogue, no proven operating M1 attainment |

`docs/contract.yaml` and the launch runbook explicitly retain missing
T8-postmerge-production-release-and-receipt and T10-remote-evidence gates.
Repository files cannot prove host settings. Agent approval remains disabled.
Local success is not acceptance; a draft PR still needs exact-head trusted CI
and human CODEOWNER review. No production records may be added before T10.

M2 requires an external inventory and reference resolution; M3 requires declared
and observed use plus measured reconciliation; M4 requires operating triggers,
incident feedback and proportionate review. These are integration dependencies,
not services being added here. Review quarterly and when release gates change.
