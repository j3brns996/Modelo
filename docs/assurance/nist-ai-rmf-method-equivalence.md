# NIST AI RMF method equivalence

Modelo supports selected NIST AI RMF inventory outcomes. Modelo does not by
itself make an organisation NIST compliant, nor does it constitute the complete
organisational AI-system inventory. **Not a certification.**

The [AI RMF 1.0 Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
describes outcomes, not an ordered checklist. GOVERN 1.6 addresses inventory
mechanisms and risk-prioritised resources. The final
[Generative AI Profile, NIST AI 600-1, page 16](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf#page=20)
adds suggested actions for enumeration (GV-1.6-001), embedded GAI inventory
treatment (002), and inventory content (003). Use the final profile: the
initial draft used different action ordering.

## Assessable method-equivalence test

These are organisation-defined classifications, **not a NIST maturity scale**:

| Level | Required interpretation |
|---|---|
| N | Not addressed |
| S | Supporting evidence only; another method owns the outcome |
| P | Partial outcome with explicitly stated gaps |
| D | Design-equivalent within a precisely bounded scope; demonstrated design covers that scope |
| O | Operating-equivalent over an actual independently assessed operating period |

Assess each of seven dimensions, recording gaps rather than averaging them:

| Dimension | Assessment question |
|---|---|
| Intent | Does the method accomplish the selected outcome? |
| Scope | Which population, component and exclusions are covered? |
| Mechanism | What repeatable controls produce it? |
| Authority | Who owns acceptance and who can change it? |
| Evidence | What attributable artefacts demonstrate the result? |
| Timeliness | How are stale observations and material changes handled? |
| Failure behaviour | What happens when evidence, controls or dependencies fail? |

D requires a reviewer to find no material design gap within the declared
component scope. O additionally requires elapsed period dates, assessor,
population/sample, findings, dated operating evidence, remediation disposition
and independent review. Schema-valid assertions alone do not prove truth.
This non-operating repository profile rejects current O, even with a filled-in
assessment form. A separately governed operating assessment profile must verify
real evidence before changing that rule. Tests, documentation and synthetic builds cannot establish O. Evidence must
demonstrate actual operation across the stated period and population.

## Mapping and reverse lookup

[nist-ai-rmf-mapping.yaml](nist-ai-rmf-mapping.yaml) is the authoritative
machine-readable mapping. `modelo.assurance.validate_mapping` checks its
schema, unique outcomes, references and elapsed assessment periods against an
explicit `as_of`. `reverse_mapping` deterministically derives artefact-to-outcome
links from that same source; there is no manually maintained competing index.
Contract tests validate the mapping and documentation drift on every control PR.

Current levels: GOVERN 1.6 P; GV-1.6-001 P; GV-1.6-002 S; GV-1.6-003 P.
Only the bounded model/version/access/provenance/Condition contribution to 003
targets D. The overall action still needs external system context, issues,
oversight, rights and sensitive-data assessment. No level measures certification.

The proposed enterprise cadence is quarterly inventory completeness/resource
review and quarterly profile review; component evidence is checked per proposal.
An external inventory must handle missing or revoked Offering references as
review gaps, not permission to substitute a model or route. Discovery absence
does not automatically revoke accepted Offerings.
