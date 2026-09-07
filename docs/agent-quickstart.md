# Agent quickstart

Start with the need. Let the agent prepare the records and review material.
The requester does not need to know Modelo IDs or evidence formats.

## Request without agent setup

On the proposal page, copy the requester agent guide URL (`/agents/README.md`
under the configured site base path). Paste it into any coding agent with your
business need. The plain Markdown includes the published inventory and schemas,
examples from the same snapshot, and each proposal field's meaning and reason.
No installed skill, agent configuration, or checkout is needed for intake.
The agent prepares a native GitHub or GitLab issue form; the human submits it.
Requester intake does not use the issue API.

## Give a maintainer agent a task

Open a checkout and provide the request link, business need, intended use,
known vendor/model details, and where/when. Add known rights-owner domicile,
operator, and processing territory separately. For maintenance, invoke
[modelo-maintain](../.agents/skills/modelo-maintain/SKILL.md):

```text
Use $modelo-maintain in this repository.
Triage request <issue URL>. The team needs <outcome>.
The model/provider reference is <URL or name, if known>.
Check existing records, establish supported facts, and prepare the smallest
reviewable change. Report unknowns and required human decisions.
```

The agent reads `AGENTS.md`, `modelo.yaml`, the contract, and relevant schemas.
It can inspect records, gather read-only evidence, explain gaps, and prepare a
draft. Existing authorization governs remote writes. The skill does not grant
new permissions. Native GitHub or GitLab forms remain available for human
review and submission.

## Route the work

| Work | Skill | Output |
|---|---|---|
| Triage, maintenance, or uplift | [modelo-maintain](../.agents/skills/modelo-maintain/SKILL.md) | Reviewable change or a bounded design recommendation |
| Provider observations | [modelo-discover](../.agents/skills/modelo-discover/SKILL.md) | Evidence candidates with retrieval scope and time |
| Catalogue records | [modelo-change](../.agents/skills/modelo-change/SKILL.md) | A linked MAC and evidence-backed candidate |
| Independent review | [modelo-review](../.agents/skills/modelo-review/SKILL.md) | Exact-head findings from an eligible independent reviewer |

The author cannot supply independent review. Agent approval is disabled.
Human CODEOWNER approval is required for maintenance changes. Agents do not
merge. A simple request is triage; it is not a canonical MAC or approval.

## Verify and hand off

Use the Python and uv versions pinned in `modelo.yaml`.

If the installed `uv` is older or reports a lockfile/configuration error, run
the pinned executable through the tool runner. This keeps the command identical
across Windows, macOS, Linux, and CI:

```bash
uv tool run --from uv==0.11.33 uv sync --locked
uv tool run --from uv==0.11.33 uv run --locked modelo check --base <base-sha> --head <head-sha> --as-of YYYY-MM-DD
```

Run narrow tests first. Include the issue, diff, base/head/tree SHAs, test
results, and trusted CI reference in the change request. A local pass does not
replace successful trusted CI for the exact head. A new commit requires new
checks and review. Do not add production catalogue records before remote T10.

## Assess system requirements and capacity

Start a system assessment when accepted changes reach 5-10 per working day,
or a consumer needs an API contract. This is separate from offering and record
approval. It does not add approval steps. Above 10 per day, reassess approval and
publication capacity promptly. Record measured volume, delays, and consumer
requirements. Do not present thresholds as evidence of a current bottleneck.

Assess performance, availability, security, recovery, and cost as system NFRs.
Define the API contract before choosing infrastructure: consumers, data and
operations, stable identities, versions, access controls, errors, and service
expectations. Existing static JSON or release snapshots may meet the need.
An application API or operational store needs a separate human-reviewed system
change. See [system assessment criteria](../SPEC.md#system-requirements-and-capacity-assessment).
