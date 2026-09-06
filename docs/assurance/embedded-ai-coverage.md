# Embedded AI: covered-by-parent

Covered-by-parent means that an embedded AI capability does not require a
separate inventory entry because it is adequately represented within an
inventoried parent application or AI-system record. It is not exempt from
governance, ownership, risk management, supplier management, incident handling
or lifecycle control.

The external organisational inventory owns this determination. The following
seven criteria are a proposed **enterprise policy**, not verbatim NIST rules.
All must hold:

1. No materially distinct purpose is introduced.
2. Accountability remains with the same owner.
3. Data, affected parties and consequences remain within the parent envelope.
4. The organisation does not separately select or manage the model route.
5. The parent record adequately identifies the capability.
6. No high-impact, consequential or autonomous use is introduced.
7. Material changes trigger reassessment.

If any criterion fails, require a separate external AI-use entry. Do not add
every embedded SaaS feature to Modelo. A separately known and governed route
may reference an Offering; a supplier's undisclosed model must not be guessed.

## Non-authoritative integration example

```yaml
kind: InventoryCoverageDetermination
feature:
  supplier: example-supplier
  product: enterprise-productivity-suite
  name: meeting-summarisation
coverage:
  mode: covered-by-parent
  parent_system_ref: cmdb:business-application:BA012345
  policy_id: ai-inventory-scope
  policy_version: 2
criteria:
  distinct_purpose: false
  distinct_owner: false
  materially_different_data: false
  affected_parties_within_parent: true
  consequences_within_parent: true
  consequential_decision: false
  high_impact_use: false
  autonomous_use: false
  separately_managed_model_route: false
  parent_identifies_capability: true
  material_change_reassessment: true
underlying_model:
  status: not-disclosed
modelo:
  offering_urn: null
review_triggers:
  - purpose-changed
  - sensitive-data-introduced
  - autonomous-action-enabled
  - supplier-terms-changed
  - underlying-provider-changed
```

This is not a core Modelo entity, approval record or deployable policy. Its
owner must retain the actual determination, parent record and policy version.
