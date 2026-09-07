# Modelo v0.1 launch runbook

This runbook records completed bootstrap history, the current control posture
and the remaining production launch gates. The checked-in Pages workflow may
publish the labelled synthetic demo after merge. That demo proves only the
static hosting path; it is not a MAC approval, final release receipt,
production catalogue or T10 completion.

## Completed bootstrap history

The bootstrap PR was the accepted exception that brought up the control plane.
Before merge it contained no production model or offering records, the reviewed
head SHA and head tree were recorded, the locked test suite and offline package
build ran on that head, T6/T8/T9 were independently reviewed, and every
control-plane path received human CODEOWNER review. The PR was squash-merged
only after the resulting tree was confirmed to match the reviewed head tree.

After merge, the main tree was verified to equal the reviewed head tree. The
checked-in Pages workflow now publishes the synthetic demo, and the first demo
verification exercises search, multi-select filters, sorting, result counts,
table/grid persistence with URL precedence, a copied URL and two-model
comparison with keyboard input. Presentation QA also checks the published
Alpine CSP runtime, third-party notices, desktop/mobile shells, remote font
origins, overflow and no-JavaScript record access.

## Current control posture

Apply and read back: PR required; one independent approval; stale approvals
dismissed; last pusher cannot supply the accepting approval; branch current;
conversations resolved; force push and deletion denied; Actions default token
read-only; action SHAs pinned; Pages source set to Actions; `catalogue-*` tags
protected. The required check name is exactly `modelo/check`.

GitHub Free cannot provide every paid organisation control. Any unavailable
control is recorded as an explicit capability failure, never treated as
present. GitLab's checked-in job is deliberately fail-closed until a protected
pipeline policy or equivalent is configured and rehearsed.

Gate C remains mandatory: create `j3brns996/Modelo-rehearsal` from the exact
bootstrap tree, override only the globally owned repository and Pages
coordinates in `modelo.yaml`, and use it for sentinel records and destructive
protection tests. Run one factual synthetic condition-add MAC through issue,
PR, exact-head check, independent approval and squash merge. Retain
`check.json` and the validation site, then prove the negative cases for invalid
data, failed tests, stale head, stale base, spoofed check, ineligible approval,
unresolved conversation, direct/force push, branch deletion and
skipped/cancelled check.

The repository currently has no enabled agent actor. A data-only agent approval
is impossible until a distinct platform identity is registered and enabled.
The author, committer and last pusher cannot supply the independent approval.
If no second eligible identity exists, stop: do not lower the approval rule.

## Remaining production launch gates

### Release and recovery commands

Run `uv run --locked modelo platform capabilities` to inspect GitHub ruleset
enforcement. A failing probe prevents release. The 7 September 2026 observation
found missing independent approval controls, a required trusted check and tag
protection. This probe does not establish T10 completion or configure controls.

The governed release workflow accepts a merged MAC PR number, its latest
successful pre-merge synchronize run ID, and a `catalogue-YYYYMMDD.N` tag.
It fetches the accepted PR head and merge, verifies provider checks and an
independent exact-head CODEOWNER approval, builds once, and verifies uploaded
assets. Synthetic releases can publish to Pages. Private releases require a
private repository and remain restricted release assets.

Configure `MODELO_RELEASE_TOKEN` with access to this repository only: Contents
write; Administration, Actions, Checks and Pull requests read. The workflow does
not expose this credential to the quality step. Existing matching release bytes
are reusable; different bytes are rejected. Host administrators still control
remote asset deletion. The workflow does not claim immutable host storage.

From a clean, pushed checkout with pinned Linux Python and uv, export locally:

```sh
uv run --locked modelo dev recovery-export --output /safe/path/modelo-recovery.zip
```

Keep the returned SHA-256 separately. Restore into a new local directory:

```sh
uv run --locked modelo dev recovery-restore \
  --bundle /safe/path/modelo-recovery.zip --sha256 sha256:EXPECTED_DIGEST \
  --output /safe/path/restored-modelo
```

The export includes a fresh remote Git mirror, host metadata, available trusted
CI artifacts, release assets, locked Python wheels and pinned UBS source. Missing
or expired historical CI artifacts are recorded explicitly. Published catalogue
releases must retain their durable receipts. An archive cannot recover evidence
already deleted by the host.

Restoration verifies the archive, Git objects, Python pin and locked wheel bytes,
then installs locally without dependency resolution or package downloads. Use
the restored environment's `modelo-local-ci lint --root .../worktree
--ubs-source .../ubs` to run lint and UBS from those files. System prerequisites
remain Linux, the pinned Python and uv, Git, Bash, jq, ripgrep and timeout.
Run an offline publication rebuild and receipt comparison before accepting the
recovery rehearsal; successful installation alone is insufficient.

Local recovery does not recreate GitLab issues, reviews or protections. The
approved isolated GitLab target is `https://gitlab.com/julianburns/modelo` under
`julianburns`; verify it is still empty before pushing restored branches and tags.
Retain archived GitHub host metadata and record GitLab capability differences.
The GitHub reviewer identity is `j3brns`. The repository licence remains undecided
at the owner's instruction.

Production launch remains blocked until a further human-approved PR implements
and tests all of the following. The public synthetic demo workflow does not
satisfy these production items:

- consume the accepted exact-head check receipt after merge;
- prove merge tree equals accepted head tree;
- build the final site once and deploy those exact bytes to Pages;
- write and validate the detached release receipt;
- create and verify a protected `catalogue-YYYYMMDD.N` release;
- export a checksummed recovery bundle and restore it offline;
- restore to an isolated GitLab project and record capability differences;
- record keyboard and screen-reader evidence;
- record the owner's explicit repository licence decision; public visibility
  alone does not grant reuse rights.

This deferral is an explicit launch contract, not accepted technical debt. No
production catalogue data, agent approval or launch claim is permitted before
Gate D and the full T10 evidence set pass.
