# ELI21: What Modelo does and how it fits AI governance

A model name is not a permission to use it. Modelo keeps the model's identity
separate from the decision about how your organisation may consume it.

Consider this illustrative example—not an enterprise approval:

- **Nova 2 Lite** is a named model release: what the model is.
- **Nova 2 Lite through Bedrock in eu-west-2** is a possible Offering: an
  approved way to consume that release, with evidence, routes and Conditions.
- **Customer-call summarisation in Adviser Desktop** is an organisational AI
  use: where and why the organisation uses that component.
- **Meeting summarisation in a productivity suite** may be covered by the
  parent product's inventory entry if all coverage criteria hold.

Modelo's existing `Model` record means ModelRelease. Its stable internal ID
does not pretend that a universal vendor-neutral identifier exists. External
identifiers are namespaced, evidenced claims. Matching display names through
two providers do not prove the same release—and never make those consumption
paths the same governance object. Residency, routing, contracts and controls
can require different Offerings even for one release.

A provider listing proves an observation in a particular scope, not enterprise
approval. Modelo records the approved component, evidence and versioned
Conditions in Git. An external AI-system inventory records purpose, owner,
data context, affected parties, oversight and lifecycle. It references a stable
Offering URN and resolves that reference against accepted catalogue provenance.

Embedded AI can be **covered-by-parent** when its purpose, ownership and risk
context remain inside the inventoried parent envelope and the other criteria
hold. That avoids duplicate inventory entries, not governance: supplier
management, incidents, ownership and change review still apply. Separately
managed routes or consequential/autonomous uses require their own external
AI-use entry. If a supplier does not disclose its model, record that uncertainty;
do not fabricate a Modelo mapping.

An agent can gather read-only evidence and prepare one proposal containing a
ModelRelease, its first Offering and evidence. There is no need for two approval
loops. Trusted CI checks the exact commit and an authorised independent reviewer
decides whether to approve it. Any new commit invalidates that evidence. Agent
approval is disabled; this control-plane change requires a human CODEOWNER.

NIST method equivalence asks whether a method demonstrably delivers a comparable
outcome within a stated scope. It is not a compliance badge. Modelo supports
selected inventory outcomes but is neither a certification nor a complete
organisational AI-system inventory. Its synthetic demonstration is not production
operating evidence; production publication and T10 gates remain outstanding.
