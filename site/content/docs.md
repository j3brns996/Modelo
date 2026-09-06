Start with the human specification if you want to understand why Modelo works this way. Use the machine contract and JSON Schemas when you need the exact record shapes and validation rules.

An offering now includes an `approval_rationale`: a policy-authored explanation of why that particular way of consuming a model is approved. The change request separately records its `purpose`, `reason` and `acceptance` checks.

For local validation, clone the repository and use the locked Python and uv toolchain. Node, npm and npx are not required.

For proposal drafting, start with the [interactive helper](/Modelo/propose/#builder) or read the repository's `docs/authoring.md`. The page keeps all five governed operations in its static chooser. Its interactive helper covers add and change only.

The browser helper and `modelo dev` commands prepare drafts. They do not approve a change, establish evidence admissibility or replace the linked issue and trusted compiler.

## Assurance: NIST AI RMF

Supports selected NIST AI RMF outcomes

Not a certification

Not a complete organisational AI-system inventory

Modelo supplies governed ModelRelease, Offering, route, evidence and Condition
components. An external inventory owns AI uses, purposes, owners and human
oversight. Embedded AI may be covered-by-parent; this is not exemption from
governance. M1 is the governed component registry target, not demonstrated
production operation. Production release automation and T10 remain outstanding.

See the repository's docs/eli21.md and docs/assurance/nist-ai-rmf-mapping.yaml
for the explanation, mapping, proposed assessment criteria and limitations.
