# Static catalogue site contract

The site is a deterministic view of validated repository state. It is not an
application, performs no authentication and calls no Modelo or cloud API.
`openmodels.run` is the primary browse/compare UX reference; its live API,
accounts, telemetry and service architecture are explicitly not copied.

## Source and output

```text
site/
  templates/{base,home,catalogue,model,offering,changes,process,propose,docs,404}.html
  assets/{site.css,catalogue.js,proposal.js,vendor/alpine-csp-3.16.3.min.js,vendor/THIRD-PARTY-NOTICES.md}
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
presentation uses locally available Georgia, system-ui and ui-monospace fonts.
No font service or remote asset request is required. No Node, npm or `npx`
command is required for the locked build.

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
equal the fixed list in `docs/contract.yaml`—base route HTML, five local assets,
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
| `propose` | `/propose/` | Five static links to configured add/change/revoke/move/batch intake, plus a guided draft for all five operations |
| `docs` | `/docs/` | Specification, contract, schemas and clone commands |
| `overview` | `/overview/` | 5W+H, entity relationships, file keys, Git rationale, review criteria, and scope |
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
storage falls back to the configured table view without breaking the explorer.
The catalogue route alone loads `catalogue.js` followed by the vendored Alpine
CSP runtime. The propose route alone loads the independent vanilla
`proposal.js`; it does not load Alpine or catalogue logic. Every other route
contains no browser runtime.

The propose route's five operation cards always resolve from
`repository.web_routes.mac_intake` and work without JavaScript. Its optional
interactive draft covers all five operations and directs each draft to that
operation's configured intake URL. The displayed issue-field summary is
non-canonical convenience output: it has no request UUID, keys or digest and is
never MAC metadata. The complete final percent-encoded `URL.href`, including
the configured query and every proposed issue field, is limited to 7,000
characters. This leaves conservative headroom below common 8 KiB
infrastructure limits. At or below the limit the configured query is preserved
and the complete fields are appended. On overflow the destination remains the
untouched configured intake URL: no partial user fields are applied, and the
full displayed summary remains available for manual entry.

Validation, URL-building and clipboard-copy outcomes use separate status nodes. Each is an
atomic polite live region (`aria-live="polite"`, `aria-atomic="true"`), so one
action cannot overwrite or conceal the assistive-technology result of the
other. All operations also retain their static cards. Trusted
default-branch intake tooling creates and validates the canonical payload after
a Git-provider issue exists.

The shared shell uses warm paper, dark ink, restrained teal, system serif
headings and sans-serif controls. It has no remote fonts, gradients or blur.
Navigation, a single synthetic notice and the footer are shared across routes.
Home leads with search, followed by a compact publication summary and a reading
guide. The catalogue defaults to a table; model cards remain an explicit choice.
Search and facet changes update visibility without repeatedly reordering nodes.
Detail pages put approved access and its conditions before supporting evidence.
At narrow widths, navigation wraps and the composer and lookups stack.

`site/content/proposal-fields.json` supplies field labels, explanations, options
and applicability. Native GitHub forms and GitLab Markdown templates retain the
same explanations, checked by tests. Lookups next to prescribed fields use only
the validated publication projection. Selection is explicit; new identities are
never inferred from names, and an absent lookup match does not prove availability.
Switching operations preserves values while excluding inapplicable answers.
Invalid drafts display field errors and cannot open a prefilled form.

GitHub handoff includes an explicit `title`, derived from the operation and
first subject ID (bounded to 255 characters), plus each native text field by
its existing ID. Composer dropdown choices are carried as text values. The
GitHub templates use prefillable text controls for these prescribed choices,
show their allowed values and default to the first listed choice (or the fixed
operation). The trusted compiler still rejects values outside its enums.
Native GitHub dropdown URL values are not relied upon: live testing with both
option names and numeric indices left them unselected after hydration.
Human attestation checkboxes remain unchecked.

GitLab handoff is ordinary browser navigation, using `issue[title]`,
`issue[description]` and `issue[issue_type]=issue`. It requires no browser API
token or CORS integration. GitLab 18.1 EE documents `/-/issues/new`; use the exact
configured route and verify alternatives such as `/-/work_items/new` on the
installed instance. Named template parameters are removed when supplying the
full description. On 18.1 a default template can still be appended: the human
must retain one set of answer headings. Attestations remain unchecked.
Authenticated submission and default-template behavior require deployment tests;
local transport tests do not establish that the target instance is ready.

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

The existing documentation route also serves a plain-language field guide to
browse/discover/MAC/system-change modes and accountable roles. Home links directly
to the interaction and NIST sections using the configured docs route. Two inline
SVGs have accessible names, descriptions and adjacent prose; they require no
JavaScript or external rendering service. The NIST summary retains the published
P/P/S/P mapping, M1 target and non-certification/incomplete-inventory limitations.
Material for MkDocs could be a separately integrated design subsite, but is not a
dependency or a second publication pipeline in this change.

Model detail pages display the derived internal ModelRelease URN, effective label,
precision, optional date and namespaced identity claims with their statuses.
An omitted release object is labelled as the implicit Modelo named-release
baseline; absent dates and claims are not invented. All values are escaped text.
Claim status is not Offering approval. Machine-readable publication preserves
source identity fields and evidence pointers without adding presentation defaults.

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

## Request form and access test

The primary form collects four answers: optional vendor/model/link, required
business need, required intended use, and optional where/when. Each is bounded
to 2,048 characters. It creates a
triage request, not a canonical MAC. `repository.web_routes.request_intake`
selects the native form. The detailed composer is collapsed by default; an
explicit operation or contained fragment opens it. Both forms retain copy
fallbacks and open native forms in a fresh tab.

Only the GitLab proposal page offers a user-triggered GUI repository GET.
Its CSP permits connections to the configured repository origin and self.
No other route gains a remote connection source. The test uses session cookies
where browser policy permits, does not follow redirects, and times out after
ten seconds. It reports HTTP status or an indeterminate result; it does not
infer authentication from 200 or gate submission. Cross-origin responses need
GitLab CORS support. The build itself remains offline.

## Writing and diagrams

Apply the [Microsoft Writing Style Guide](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)
to authored prose, field help, captions, and diagram labels. Lead with the fact
or action. Use short sentences, active voice, sentence case, and consistent
entity names. Keep claims objective. Preserve schema keys, protocol headings,
source quotations, and historical records exactly where their meaning depends
on the original text.

The overview uses static SVG with accessible titles, descriptions, captions,
and adjacent text. Its ER diagram distinguishes file identities and validated
references from database PK/FK constraints. Model artifacts and embedded AI in
vertical products remain outside the current component catalogue scope.
Embedded AI still requires organizational risk management; NIST does not grant
an exemption. Integration work is tracked in issue 78.

The shared navigation includes a labelled GET search form for the existing
catalogue search. It sends a bounded `q` query to the configured catalogue
route and adds no browser runtime. It searches models and offerings; it is not
a full-text documentation index. At narrow widths, the form wraps below the
navigation links.

The overview separates offering/record approval from system NFR and API-contract
assessment. The latter concerns performance, availability, security, recovery,
cost, and consumer interfaces. Its 5-10 accepted changes/day signal adds no
record approval steps. The agent quickstart links to the portable maintainer
skill and preserves human approval and exact-head CI requirements.

Optional request checkbox groups capture model rights-owner domicile and data
processing territory separately (UK, EU, China, USA, Other), plus operator
(AWS, Azure, Google Cloud, Other). All start unticked. These are unverified
request details, not approval or new core catalogue facts. GitHub handoff uses
prefillable text fields for these selections; GitLab Markdown uses marked
choices. Unknown domicile never supplies a default processing territory.

Clear comparison resets selected models, the comparison dialog, and `compare`
URL parameters. It preserves search and filters and returns focus to catalogue
search. The button is available beside comparison controls when a selection exists.
