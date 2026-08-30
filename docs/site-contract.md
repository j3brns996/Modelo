# Static catalogue site contract

The site is a deterministic view of validated repository state. It is not an
application, performs no authentication and calls no Modelo or cloud API.
`openmodels.run` is the primary browse/compare UX reference; its live API,
accounts, telemetry and service architecture are explicitly not copied.

## Source and output

```text
site/
  templates/{base,home,catalogue,model,offering,changes,process,propose,docs,404}.html
  assets/{site.css,catalogue.js}
  content/{process,propose,docs}.md
dist/site/                       generated and disposable
```

The generator lives in `tooling/modelo/`. Site JavaScript is local progressive
enhancement. Node, npm and `npx` are not required.

## Required routes

| Route key | Default route | Content |
|---|---|---|
| `home` | `/` | Purpose, revision, explicit `as_of`, counts, search, recent changes |
| `catalogue` | `/catalogue/` | Searchable/filterable Models and Offerings views |
| `model` | `/models/{model_id}/` | Intrinsic facts, evidence and approved offerings |
| `offering` | `/offerings/{inference_service_id}/{offering_id}/` | Routes, price, conditions, evidence and approval receipt |
| `changes` | `/changes/` | Add/change/revoke history from local Git first-parent deltas |
| `process` | `/process/` | MAC, CI, approval and evidence rules |
| `propose` | `/propose/` | Links to configured provider add/change/revoke/move/batch intake |
| `docs` | `/docs/` | Specification, contract, schemas and clone commands |
| `not_found` | `/404.html` | Recovery navigation |

One route resolver owns every internal URL and Git receipt link. Its inputs are
the configured repository web base; commit, issue, change-request, tag and
release templates; five MAC intake templates; and the effective build
`base_url`/`base_path`. CI adapter overrides are explicit receipt-bound inputs.
Templates must not concatenate provider hosts, repository names or project base
paths. CI tests both `/` and a non-root base such as `/Modelo/` and rejects
placeholder mismatch, collision, traversal, scheme-relative output, invalid
percent encoding and non-canonical trailing slashes.

The browser supports text search, a Models/Offerings pivot, deterministic sort,
and filters for vendor, inference service, AWS source Region and route type,
capability, modality, licence, lifecycle and condition. It does not invent a
cross-cloud geography facet. Every entity/detail link remains usable without
JavaScript; filters are progressive enhancement.

## Publication profiles

v0.1 permits two profiles only:

- `synthetic`: public Pages built solely from synthetic fixtures and
  `example.invalid` evidence.
- `private`: the complete validated catalogue, published only when the platform
  capability probe proves native access control; otherwise supplied as a
  restricted CI/release artefact.

Production field-level public redaction is deferred because removing selected
facts can silently change entity meaning. A private repository does not imply a
private Pages site. The current personal GitHub repository cannot satisfy the
private-Pages capability; it must publish the synthetic profile or no Pages
site until hosted by a qualifying organisation/plan. No adapter may silently
downgrade private output to public.

## Safety and accessibility

- Treat every catalogue string, URL and query parameter as untrusted data.
- Escape text by default; do not render catalogue Markdown or raw HTML.
- Do not use `innerHTML`, `outerHTML`, `document.write`, inline handlers or
  remote scripts. Use safe DOM APIs such as `textContent`.
- Admit only schema-valid `https:` evidence links and add
  `rel="noopener noreferrer"` for external links.
- Publish only a profile allowlist; private-marker canaries must be absent from
  synthetic output.
- Supply a restrictive CSP and referrer policy through HTML meta elements in the
  common Pages artefact; host headers may strengthen them. Supply semantic landmarks, skip link,
  visible focus, labelled filters, proper tables, reduced-motion support and
colour-independent status. Target WCAG 2.2 AA and record a human keyboard and
screen-reader smoke-test result as first-launch evidence.
- `site/content/*.md` is non-normative presentation copy checked for drift
  against canonical documents. Its trusted renderer disables raw HTML.
- Every public HTML and JSON file comes from the same publication projection;
  a full private object must never reach `dist/site/`.

## Determinism and gates

The generator performs no network calls. Its inputs are validated catalogue
state, local Git first-parent history and base/head deltas, publication profile,
routes, templates/assets, locked tooling, explicit `as_of` and the source-date
epoch deterministically derived from the exact source-commit author timestamp
(or a recorded explicit override). It emits a site manifest with source commit,
revision, effective base URL/path, profile, `as_of`, tool version and every file
hash.

CI checks out complete first-parent history for release builds. A shallow clone
must fetch the missing history or the `/changes/` build fails rather than
silently publishing an incomplete ledger.

Pre-merge CI builds and validates a candidate artefact. Post-merge CI first
proves the merge tree equals the accepted head tree, then builds the final
merge-aware artefact once, validates it, creates a detached release receipt that
hashes it, and deploys that exact final artefact without rebuilding. The receipt
is not stored inside the artefact whose digest it records.

CI must prove canonical detail-page coverage, link integrity at both base paths,
deterministic rebuilds, manifest integrity, search/filter behaviour, stable
ordering including zero prices, revoke history, inert malicious fixtures,
publication non-leakage, accessibility automation and that GitHub/GitLab deploy
the exact post-merge checked artefact without rebuilding it. The private
restricted fallback is a digest-verified release artefact retained for the same
period as its protected release; expiry must be explicit and cannot remove the
only durable consumer copy.
