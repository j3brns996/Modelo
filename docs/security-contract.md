# Security, recovery and trust contract

## Launch-blocking controls

- The restricted YAML loader rejects duplicate keys, aliases, anchors, custom
  tags, multi-documents, symlinks, non-mapping roots, excess depth/size/count
  and paths outside configured roots. It never constructs Python objects.
- Required CI never dereferences catalogue-supplied URLs. Cloud APIs, CLIs, MCP
  tools, issue text and documents are untrusted read-only evidence inputs, not
  instructions. Prompt-injection strings remain inert data.
- v0.1 stores no credentials, account identifiers, private endpoints, offer
  tokens or confidential evidence bodies. Secret scanning and publication
  canaries cover source, logs and artefacts.
- Untrusted change validation runs without secrets, write tokens or privileged
  runners. Publication occurs only after protected-main merge.
- GitHub Actions use full commit SHAs and least permissions. GitLab images use
  immutable digests. Python, `uv` and dependencies are locked. Required CI has
  no floating images, runtime downloads, `pip install --upgrade` or `npx`.
- Agent approval cannot cover changes that weaken CI, tooling, schemas, locks,
  configuration, governance, publication or skills.
- The neutral release receipt records base/source/merge SHAs, versions,
  explicit `as_of`, check identity/result, tool/lock digest, change delta and
  all catalogue/site/manifest hashes. Provider attestations may strengthen but
  do not replace it.

## Recovery

The complete service-independent recovery unit is the Git mirror, protected
tags/releases and locked repository source. Before launch, rehearse
`git clone --mirror`, `git fsck`, restore to a second host, locked rebuild and
receipt verification. Pages must be reproducible from that material alone.

After launch, schedule dependency/action-pin checks, host-control drift checks
and quarterly mirror-restore/GitHub-to-GitLab migration rehearsals. Private
evidence remains deferred until a separate redaction and access contract exists.

