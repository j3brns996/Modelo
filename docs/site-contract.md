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
dist/candidate/site/             pre-merge generated and disposable
dist/final/site/                 post-merge generated and disposable
dist/receipts/                   detached; never publication members
```

The generator lives in `tooling/modelo/`. Site JavaScript is local progressive
enhancement. Node, npm and `npx` are not required.

T5 supplies one validated canonical catalogue projection and canonical change
delta. Its candidate is exactly `data/catalogue.json`,
`data/change-delta.json` and the non-recursive manifest that hashes those two.
T6 does not trust the mutable candidate directory. It repeats the T5 acceptance
boundary against the accepted source commit and validated MAC metadata, rebuilds
those exact bytes deterministically, and must not perform a second raw/private
catalogue serialisation.
It adds the final site bytes and complete `data/manifest.json` defined by
`schemas/build-manifest.schema.json`. The manifest lists every publication file
except itself. T8 supplies trusted provider metadata and creates the detached
check receipt; only post-merge publication may create the final receipt.

Completeness ownership is split: T5 enforces the exact candidate set above;
T6 owns the executable final exact-set rule. Final manifest `files` keys must
equal the fixed list in `docs/contract.yaml`—base route HTML, two local assets,
`data/catalogue.json` and `data/change-delta.json`—union every schema file
beneath the configured schema root at the exact source commit, union
`models/{model_id}/index.html` for every projected model and
`offerings/{inference_service_id}/{offering_id}/index.html` for every projected
offering. `data/manifest.json` is deliberately excluded. Missing fixed files,
missing detail pages and unexpected extra files each fail dedicated negative
tests; JSON Schema validates the wire shape but does not derive this inventory.

## Required routes

| Route key | Default route | Content |
|---|---|---|
| `home` | `/` | Purpose, revision, explicit `as_of`, counts, search, recent changes |
| `catalogue` | `/catalogue/` | Searchable/filterable Models and Offerings views |
| `model` | `/models/{model_id}/` | Intrinsic facts, evidence and approved offerings |
| `offering` | `/offerings/{inference_service_id}/{offering_id}/` | Routes, price, conditions, evidence, approval coordinates and protected release/receipt discovery link; no embedded receipt claim |
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

T6's Python generator produces the AWS Region view from validated T5 data. It
labels `route.source_region` as **Source Region**. For a direct route it emits
no destination set. For a system profile it follows each explicit destination
binding to its foundation-model evidence and labels that evidence source Region
as **Destination Region**. Templates and browser JavaScript consume only this
build-produced view; they must not parse ARNs or infer Regions. Two routes that
use the same ID-form profile reference in different source Regions remain
separate rows, and pricing remains associated by route ID.

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
  a full private object must never reach a synthetic publication directory.

## Determinism and gates

The generator performs no network calls. Its inputs are validated catalogue
state, local Git first-parent history and base/head deltas, publication profile,
routes, templates/assets, locked tooling, explicit `as_of` and the source-date
epoch explicitly supplied and required to equal the exact source-commit author
timestamp. Environment values and arbitrary overrides are forbidden. Final
uses the accepted head author timestamp; merge time may be separate receipt
metadata but is never the build epoch. It emits a site manifest with source commit,
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

Each build exclusively acquires the fail-fast writer lock, journals its phase,
creates `dist/candidate.<id>.staging` or `dist/final.<id>.staging` beside its
target using 128 OS-CSPRNG bits, with the matching `<target>.<id>.backup`, fsyncs
and validates the staged tree, renames the old target to a backup, renames the
stage to target, fsyncs and verifies it, then removes the backup and lock.
Handled failure restores the backup. Crash recovery is explicit and
journal-driven; ambiguity fails closed. The two renames are not one globally
atomic transaction: readers may see complete-old, complete-new or temporarily
absent, never partial. Final builds require file and directory fsync support.
File digests are SHA-256 over exact bytes; the publication digest hashes sorted
path/NUL/digest/NUL/size/LF records, so archive metadata is irrelevant.

The effective URL is lowercase-host HTTPS with implicit port 443, no
userinfo/query/fragment and a trailing slash. T8 requires its URL path to equal
normalised `base_path` exactly and tests both `/` and `/Modelo/`.

CI must prove canonical detail-page coverage, link integrity at both base paths,
deterministic rebuilds, manifest integrity, search/filter behaviour, stable
ordering including zero prices, revoke history, inert malicious fixtures,
publication non-leakage, accessibility automation and that GitHub/GitLab deploy
the exact post-merge checked artefact without rebuilding it. The private
restricted fallback is a digest-verified release artefact retained for the same
period as its protected release; expiry must be explicit and cannot remove the
only durable consumer copy.

Test ownership is deliberately split. T6 owns static no-JavaScript navigation,
links, inert malicious fixtures, non-leakage and automated accessibility
structure. T8 owns pinned Python-controlled browser execution outside the core
build runtime. T10 records human keyboard and screen-reader smoke evidence.
