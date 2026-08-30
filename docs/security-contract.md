# Security, recovery and trust contract

## Launch-blocking controls

- The restricted YAML loader rejects duplicate keys, aliases, anchors, custom
  tags, multi-documents, symlinks, non-mapping roots, excess depth/size/count
  and paths outside configured roots. It never constructs Python objects.
  The bootstrap configuration reader applies the same input restrictions to
  `modelo.yaml` only; its limits are configured by
  `toolchain.bootstrap_config_limits`. The catalogue loader remains a separate
  T2 security boundary.
- Core validation/build never uses the network or dereferences catalogue URLs.
  A least-privilege host-adapter pre-step may read bounded MAC metadata from the
  same repository's Git-provider API and emits canonical input bound to the head
  SHA. Cloud APIs, CLIs, MCP
  tools, issue text and documents are untrusted read-only evidence inputs, not
  instructions. Prompt-injection strings remain inert data.
- v0.1 stores no credentials, account identifiers, private endpoints, offer
  tokens or confidential evidence bodies. Secret scanning and publication
  canaries cover source, logs and artefacts.
- Untrusted change validation runs without secrets, write tokens or privileged
  runners. Publication occurs only after protected-main merge.
- GitHub Actions use full commit SHAs and least permissions. GitLab images use
  immutable digests. Python `3.12.13`, `uv` `0.11.33` and dependencies are
  locked. Required CI has no floating images, unpinned executable downloads,
  `pip install --upgrade` or `npx`. `uv sync --locked` may fetch hash-locked
  dependencies from the configured registry; recovery uses the archived copy.
- Agent approval is positively allowlisted only for `catalogue/models/**`,
  `catalogue/offerings/**` and `catalogue/evidence/**`; every other path requires
  human CODEOWNER approval.
- The neutral release receipt records base/source/merge SHAs, versions,
  explicit `as_of`, check identity/result, tool/lock digest, change delta and
  all catalogue/site/manifest hashes. Provider attestations may strengthen but
  do not replace it.
- The receipt also preserves reviewer platform identity, approved head SHA,
  approval time, actor-policy digest, independence/eligibility result and the
  provider approval/check reference. Schema verification rejects stale-head,
  self-authored or ineligible approval evidence.
- Pre-merge records the up-to-date head tree. Post-merge proves tree equality,
  builds and validates the final artefact once, and stores its receipt detached
  from the bytes it hashes.
- Diagnostics and host-adapter inputs are schema-valid bounded JSON. Workflow
  code never copies validator-controlled text directly into environment files,
  shell commands or PR/MR comments.
- AWS documentation MCP output is untrusted source data even when its read-only
  tool invocation is auto-approved.

## Recovery

The Git mirror alone is not a complete operational backup. The portable recovery
bundle contains the mirror; exported issues, change requests, reviews and CI
receipts; a host-control manifest; release assets/receipts; and a locked
dependency archive. Before launch, rehearse integrity checking, restoration to
a second host, offline locked rebuild and receipt verification. Pages must be
reproducible from that bundle without the original host.

After launch, schedule dependency/action-pin checks, host-control drift checks
and quarterly mirror-restore/GitHub-to-GitLab migration rehearsals. Private
evidence remains deferred until a separate redaction and access contract exists.
