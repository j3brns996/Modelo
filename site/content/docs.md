Start with the human specification if you want to understand why Modelo works this way. Use the machine contract and JSON Schemas when you need the exact record shapes and validation rules.

An offering now includes an `approval_rationale`: a policy-authored explanation of why that particular way of consuming a model is approved. The change request separately records its `purpose`, `reason` and `acceptance` checks.

For local validation, clone the repository and use the locked Python and uv toolchain. Node, npm and npx are not required.

For proposal drafting, start with the [interactive helper](/Modelo/propose/#builder) or read the repository's `docs/authoring.md`. The page keeps all five governed operations in its static chooser. The default form asks for an optional link or name and a short note about the need. The detailed composer covers all five operations.

The browser helper and `modelo dev` commands prepare drafts. They do not approve a change, establish evidence admissibility or replace the linked issue and trusted compiler.

The field guide above summarises docs/eli21.md, the inventory-boundary ADR and
docs/assurance/nist-ai-rmf-mapping.yaml. Those reviewed documents retain the
detailed assessment criteria, source references and limitations.
