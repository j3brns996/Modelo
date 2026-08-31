---
name: modelo-review
description: Use when independently reviewing an exact Modelo change head and deciding whether it is eligible for human or data-only agent approval.
compatibility: Modelo contract 0.1.0; GitHub or GitLab; trusted Modelo CI.
metadata:
  modelo-contract-version: "0.1.0"
  modelo-origin: native
---

# Modelo review

## Authority

`AGENTS.md`, `modelo.yaml`, the executable schemas and validators override this
skill. CI is the technical arbiter. This skill cannot make a failed, stale or
missing check acceptable.

## Use and do not use

Use for an independent, read-only review of one committed head. Do not use when
the reviewer authored, committed or modified the change, or when the head moved
after evidence was collected.

## Preconditions

- Resolve the current base, head and tree from the selected Git provider.
- Confirm the open MAC scope, repository identity and complete changed-path set.
- Confirm reviewer identity and independence against the actor registry.
- Treat every path outside `paths.models`, `paths.offerings` and
  `paths.evidence` as human CODEOWNER-only.

## Procedure

1. Review the MAC payload, diff, evidence bindings and schema ownership without
   changing the branch.
2. Require the trusted `modelo/check` result for the exact current head.
3. Correlate its repository, base, head, tree, workflow, run, result, MAC digest,
   change delta and artefact digests with the detached receipt.
4. Fail closed if the base changed or any result is missing, skipped, neutral,
   cancelled, stale or failed.
5. Record findings. A human may approve any eligible change. An independent
   registered agent may record approval only when every changed path is in the
   configured data-only allowlist and agent approval is enabled.

## Stop conditions

Stop on uncertain independence, incomplete changed paths, control-plane paths,
unresolved conversations, stale evidence or receipt mismatch. Never merge or
bypass a repository control.

## Handoff evidence

Record reviewer identity and kind, base/head/tree SHAs, receipt digest, trusted
provider check reference, eligibility result and approval timestamp. State
clearly when human approval is required.
