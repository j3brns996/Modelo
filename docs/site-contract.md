# Static catalogue site contract

The site is a deterministic view of validated repository state. It is not an
application, performs no authentication and calls no Modelo or cloud API.
`openmodels.run` is the primary browse/compare UX reference; its live API,
accounts, telemetry and service architecture are explicitly not copied.

## Source and output

```text
site/
  templates/{base,home,catalogue,model,offering,changes,process,propose,docs,404}.html
  assets/{site.css,catalogue.js,vendor/alpine-csp-3.16.3.min.js,vendor/THIRD-PARTY-NOTICES.md}
  content/{process,propose,docs}.md
dist/candidate/site/             pre-merge generated and disposable
dist/pages/site/                 public synthetic demo; never approval evidence
dist/final/site/                 post-merge generated and disposable
dist/receipts/                   detached; never publication members
```

The generator lives in `tooling/modelo/`. Site JavaScript is local progressive
enhancement. The exact Alpine CSP build `@alpinejs/csp==3.16.3` is vendored from
its signed npm package; its runtime SHA-256 is
`0de89ad5a626c023982c2ed7051ef5fd3cbfa22d012de81fa19005c811bfad4d`.
The standard expression-evaluating Alpine build is forbidden by the site CSP.
The Alpine and bundled Vue reactivity MIT notices are one publication member
linked from every footer. Remote application scripts remain forbidden. The
presentation loads Inter and JetBrains Mono only from the configured Google
Fonts stylesheet/file origins, both explicitly admitted by CSP. Font responses
are optional presentation resources, never generator inputs. No Node, npm or
`npx` command is required.

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

The separate `demo` build projects only the configured synthetic fixture. The
fixture contains 22 models: two fully synthetic integration records and 20
official-documentation observations used to exercise realistic catalogue
density. Documentation presence is not approval, and no route, price, licence
or regional availability is inferred for those 20 observations. Its
explicit `as_of` must equal that profile's configured fixture snapshot date; it
never substitutes the workflow wall-clock date. It
does not ingest MAC metadata, has no merge coordinate, emits an empty change
delta, and places a visible synthetic/not-approved banner on every HTML page.
It exists so the static UX, clone instructions and templates can be exercised
on public GitHub Pages before a production catalogue is authorised. It is not
the T6 final artefact and cannot satisfy a release or approval gate.

Completeness ownership is split: T5 enforces the exact candidate set above;
T6 owns the executable final exact-set rule. Final manifest `files` keys must
equal the fixed list in `docs/contract.yaml`—base route HTML, four local assets,
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
| `catalogue` | `/catalogue/` | Model-first card explorer plus complete Models and Offerings table |
| `model` | `/models/{model_id}/` | Intrinsic facts, evidence and approved offerings |
| `offering` | `/offerings/{inference_service_id}/{offering_id}/` | Policy-authored approval rationale, routes, price, conditions, evidence, approval coordinates and protected release/receipt discovery link; no embedded receipt claim |
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

The browser supports text search, multi-select facets, deterministic name/kind
sorting, a live result count, table/grid views, clearable active-filter chips,
and filters for type, vendor, inference service, AWS source Region and route
type, capability, modality, licence, lifecycle and condition. Empty facets are
not rendered. Query, filters, sort, view and comparison selection use bounded,
allowlisted URL parameters so a view is shareable; unknown values are ignored.
Facet values are ORed within a facet and ANDed across facets.
Only table/grid view preference is stored locally under the configured key.
An explicit valid URL `view` value takes precedence, and unavailable or invalid
storage falls back to the configured grid view without breaking the explorer. Catalogue
scripts are emitted only on the catalogue page; all other pages contain no
browser runtime.

The shared shell supplies sticky grouped navigation, source/publication
affordances, a synthetic-status rail and structured footer. Home leads users
through purpose, trust posture, catalogue counts, observation-to-publication
flow and next actions. Grid is the catalogue default and uses purpose-built
model-card markup rather than restyling table rows; the complete model/offering
table remains available.
Model and offering pages use the same fact, evidence, coordinate and related
record components. At narrow widths, navigation scrolls safely, split layouts
stack and the grid collapses without losing semantic table fallback.

Comparison accepts two to four canonical models only. It never compares an
offering as if it were a model and never infers facts: identifier, vendor,
capabilities, modalities, licence and lifecycle come from the already validated
projection. The dialog is built with safe DOM creation and `textContent`, never
HTML-string injection. It contains links back to complete model records and is
not an approval claim. Every entity/detail link and the complete table remain
usable without JavaScript; all explorer controls are progressive enhancement.
The comparison includes context window in addition to identifier, vendor,
capabilities, modalities, licence and lifecycle.

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

- `synthetic`: public Pages built solely from the configured demo fixture,
  including explicit synthetic records and bounded official-documentation
  observations; none is enterprise approval without a current offering.
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
- Treat URL state as untrusted input: accept only known facet values, cap search
  text at 200 characters and comparison at four known canonical model keys.
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

The GitHub demo workflow runs the complete locked test suite and offline Python
package build, reads the effective URL and synthetic fixture snapshot date only
through validated `modelo.yaml`,
builds `dist/pages/site` once, archives that exact directory with GNU tar,
uploads the single `artifact.tar` using a directly SHA-pinned GitHub-owned
artifact action and deploys without rebuilding. The Pages composite uploader is
not used because its transitive floating action reference is incompatible with
the repository SHA-pinning policy. All invoked actions are pinned to full commit
SHAs. The workflow contains no Node,
npm or `npx` command; GitHub's pinned Pages actions are provider adapters, not
Modelo runtime dependencies.

Pre-merge CI builds and validates a candidate artefact. Production post-merge CI first
proves the merge tree equals the accepted head tree, then builds the final
merge-aware artefact once, validates it, creates a detached release receipt that
hashes it, and deploys that exact final artefact without rebuilding. The receipt
is not stored inside the artefact whose digest it records.

Each build exclusively acquires the fail-fast writer lock, journals its phase,
creates `dist/candidate.<id>.staging`, `dist/pages.<id>.staging` or
`dist/final.<id>.staging` beside its
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
links, inert malicious fixtures, vendored-runtime integrity, bounded explorer
state, non-leakage and automated accessibility structure. T10 owns pinned
Python-controlled browser execution outside the core build runtime and records
search/filter/sort/view/comparison behavior plus human keyboard and screen-reader
smoke evidence.

`node tests/site/catalogue-explorer.behavior.js` is supplementary PR evidence
when a host Node executable already exists. It invokes the actual controller and
checks search/facet composition, sort/visibility, URL round-trip, URL-over-local
view precedence, storage failure and comparison bounds without npm, `npx` or a
DOM package. It is not part of `uv` acceptance and does not claim browser layout,
focus or assistive-technology behavior; those remain controlled-browser/T10 work.
