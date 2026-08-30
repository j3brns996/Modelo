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
| `offering` | `/offerings/{operator_id}/{offering_id}/` | Routes, price, conditions, evidence and approval receipt |
| `changes` | `/changes/` | Add/change/revoke history from release receipts |
| `process` | `/process/` | MAC, CI, approval and evidence rules |
| `propose` | `/propose/` | Links to configured provider add/change/revoke/move intake |
| `docs` | `/docs/` | Specification, contract, schemas and clone commands |
| `not_found` | `/404.html` | Recovery navigation |

One route resolver owns every internal URL and Git receipt link. Templates must
not concatenate `github.com`, `gitlab.com`, repository names or project base
paths. CI tests both `/` and a non-root base such as `/Modelo/`.

The browser supports text search, a Models/Offerings pivot, deterministic sort,
and filters for vendor, inference service, geography, capability, modality,
licence, lifecycle and condition. It remains usable without JavaScript.

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
- Supply a restrictive CSP, referrer policy, semantic landmarks, skip link,
  visible focus, labelled filters, proper tables, reduced-motion support and
  colour-independent status. Target WCAG 2.2 AA and require a human keyboard
  and screen-reader smoke test before first launch.

## Determinism and gates

The generator performs no network calls. Its inputs are validated catalogue
state, release deltas, publication profile, routes, templates/assets, locked
tooling and explicit `SOURCE_DATE_EPOCH`/`as_of`. It emits a site manifest with
the source commit, revision, profile, `as_of`, tool version and every file hash.

CI must prove canonical detail-page coverage, link integrity at both base paths,
deterministic rebuilds, manifest integrity, search/filter behaviour, stable
ordering including zero prices, revoke history, inert malicious fixtures,
publication non-leakage, accessibility automation and that GitHub/GitLab deploy
the exact checked artefact without rebuilding it.

