# Modelo

Find a model, check its approved access routes, or request a catalogue change.
Modelo records model facts, offering approvals, and the evidence behind each
decision. An offering links a model to a service, routes, and conditions for use.
Application owners remain responsible for their specific uses.

**Current status:** the public site is a synthetic Pages demo, not enterprise approval.
Pre-merge checks and demo publication work. Production release automation and
the remote T10 rehearsal remain outstanding.
Do not add real production catalogue data before T10 passes remotely.
Agent approval is disabled.

![Modelo: model availability passes through evidence, conditions, offering, route, and review before approved use](docs/img/modelo-title.png)

Concept illustration. Counts and status indicators are illustrative.

## Choose your next action

| Your role | Your action | Your agent's task |
|---|---|---|
| Requester | [Describe your need](https://j3brns996.github.io/Modelo/propose/), then review and submit the native issue form. | Research the need, check inventory, and prepare the form. |
| Application owner | [Browse the catalogue](https://j3brns996.github.io/Modelo/catalogue/) and check offering conditions against your intended use. | Find evidenced matches and report gaps in data, location, or oversight. |
| Record author | Start a linked request in the [issue chooser](https://github.com/j3brns996/Modelo/issues/new/choose). | Prepare records and evidence using the [authoring guide](docs/authoring.md). |
| Reviewer | Assess the proposed offering or record and the checks for its exact commit. | Independently inspect evidence, references, and CI; report findings. |
| Maintainer | Define the repository problem and desired outcome in an engineering issue. | Prepare the smallest reviewable change using the [maintainer workflow](docs/agent-quickstart.md). |

## Request a model with your agent

Give any coding agent the [requester guide URL](https://j3brns996.github.io/Modelo/agents/README.md)
and your business need. No checkout, installed skill, or agent configuration
is required. Use this prompt:

```text
Read https://j3brns996.github.io/Modelo/agents/README.md.
Our team needs <business outcome>. The intended use is <task, data, oversight>.
The model or provider reference is <official URL or name, if known>.
Research the gaps and validate against the published inventory and schemas.
Return the findings, unknowns, checks run, and a prefilled native issue-form URL.
Do not submit the form or use an issue API.
```

The guide includes worked and negative examples, reasons for each field,
host-specific instructions, exact form markup, and a proposal schema bundle.
Keep unknown facts explicit. Supply known deployment details, rights-owner
domicile, operator, and processing territory separately. A missing vendor or
service needs a prerequisite proposal before an offering can reference it.

Review the prepared answers, consider each human attestation, and submit through
your normal GitHub or GitLab login. A request starts triage; it grants no approval.
For a complete catalogue proposal, use the [detailed composer](https://j3brns996.github.io/Modelo/propose/#builder).

## Author and review records

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing records. MAC means move,
add, change, revoke, or batch. Start from a linked open MAC issue and use a topic
branch with one writer. Bind external facts to admissible evidence. Provider
availability alone does not authorize enterprise use.

Give an authoring agent the issue URL, scope, and acceptance criteria. Give an
independent review agent the change request and exact head commit. The author
cannot supply independent review. Agents do not merge. Human CODEOWNER approval
is required for control, policy, and documentation changes.

Trusted CI must pass for the exact current head. Missing, stale, skipped, or
failed checks cannot accept it. A new commit invalidates prior checks and
approval. Local helpers prepare drafts; the linked issue and trusted compiler
remain authoritative.

## Maintain the repository

Read `AGENTS.md`, [modelo.yaml](modelo.yaml), the relevant schemas, and the
[contract](docs/contract.yaml). Use the Python and uv versions pinned in
`modelo.yaml`. From a clean checkout, run:

```bash
uv sync --locked
uv run --locked modelo --version
uv build --offline --no-cache
uv run --locked modelo-local-ci run --base <base-sha> --head <head-sha> --as-of YYYY-MM-DD --jobs 3
```

Run narrow tests first. Local CI is advisory; `modelo/check` remains the acceptance
gate. Never commit generated `dist/` output. Keep system performance and capacity
assessment separate from offering and record approval.

For site builds, `--base-commit` identifies the baseline; `--source-commit` and
`--source-tree` bind output to reviewed source. Use the configured build command
in `modelo.yaml`.

Configuration owns repository paths, site and issue routes, publication profiles,
GitHub or GitLab adapter selection, and toolchain pins. JSON schemas define record
shapes. The Python validator enforces cross-record, evidence, and change semantics.
Configuration does not replace those validation authorities. [SPEC.md](SPEC.md)
explains the rationale. Workflow writes belong to the selected Git provider;
Modelo has no application API.

## Explore the demo

These screenshots show synthetic data. They are not approval, launch, or T10 evidence.

![Modelo synthetic-demo home showing navigation, synthetic status and catalogue totals](docs/img/modelo-home.png)

![Modelo synthetic catalogue showing filters and model result table](docs/img/modelo-catalogue.png)

## Find guidance and protect information

Use the [documentation index](docs/README.md) for contracts, security, and domain
guidance. Follow the [Microsoft writing style](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)
for prose and diagram labels: lead with the action, use sentence case, and keep
claims objective. Preserve schema keys and native form markers.

Read [SECURITY.md](SECURITY.md) before handling sensitive information. Do not post
secrets, tokens, private commercial terms, or private evidence in public issues.
Root repository licence and reuse terms remain undecided. Public visibility
does not grant reuse rights.
