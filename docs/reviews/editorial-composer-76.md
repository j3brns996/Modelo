# Editorial catalogue and guided proposals - issue #76

Issue: https://github.com/j3brns996/Modelo/issues/76
Baseline: b977a42. One writer on site-editorial-composer-76.

## Acceptance and implementation plan

1. Shared editorial shell: warm paper, dark ink, restrained teal, system serif headings and sans-serif controls; no remote fonts, gradients or blur. Compact table-first catalogue, readable labels, one synthetic notice, useful home and access-first detail pages.
2. Guided composer: all five operations; only applicable inputs; adjacent published-record lookups; explicit new/existing identity guidance; preserve draft values when switching sections; inline errors and readable review. No inference of missing catalogue facts.
3. Native provider handoff: shared headings and explanations across website/GitHub/GitLab; URL encoding by provider; unchecked attestations; complete 7000-character final URL bound with copy fallback. GitLab 18.1 uses configured /-/issues/new unless the deployment verifies another route. Description can append to default templates: verify no duplicate fields on the target instance.
4. Verification: meaningful composer transport and interaction tests, generated lookup isolation/escaping, adapter round trips for all operations, browser desktop/mobile/keyboard journeys, repeatable baseline/after measurements and screenshots, locked Python suite and offline package, trusted exact-head CI.
5. Delivery: open control-plane PR, monitor CI, retain branch for human CODEOWNER review, clean task-owned temporary files/processes.

## Boundaries and baseline

No production catalogue changes, cloud writes, browser API tokens, merges or T10 claims. Required check failures are never converted to passes. Main catalogue check is documented to fail on three absent production governance files. Windows lacks symlink privileges and directory fsync; Linux CI is required for those gates. Installed uv is old; use the pinned uv 0.11.33 via uv tool run.

Local preview files are disposable presentation previews, not accepting build artifacts. Browser benchmark uses the same loopback server, viewport and instrumentation before/after; it does not claim production network performance.

## Results

Implemented without new dependencies. Field definitions are shared by the generated composer and checked against all five GitHub and GitLab templates. The browser uses URL navigation only, with plain-answer validation, exact published-record lookup, operation-aware links, unchanged overflow destinations and unchecked attestations.

### Local performance observations

Chrome, loopback stdlib HTTP servers, identical benchmark script and a 1455 x 909 viewport for the paired desktop samples. Baseline is b977a42; updated preview uses the worktree sources and the same synthetic projection. Resources were warm, so these timings are diagnostic observations, not production latency claims.

| Measurement | Before | After |
| --- | ---: | ---: |
| CSS source bytes | 27,992 | 16,182 |
| Homepage DOM elements | 165 | 115 |
| Homepage load event, one paired sample | 185.0 ms | 88.6 ms |
| Search feedback, three consecutive samples | 135.3, 138.3, 133.6 ms | 2.1, 2.0, 1.9 ms |
| Search feedback median | 135.3 ms | 2.0 ms |
| External font dependencies | stylesheet + two font files | none |

The catalogue previously imposed a 120 ms debounce and sorted/appended all displayed nodes after every query. Filtering now updates visibility immediately and reorders only when sort or view changes. The benchmark compares the previous default cards with the new default table (22 versus 23 total records; both return the same nine Nova models and two Command models). It does not establish large-catalogue performance. The controller regression check verifies that repeated filtering does not append nodes again.

To repeat: build both revisions with the synthetic profile, serve them locally, open their catalogue routes in the same browser and viewport, alternate `nova` and `command`, and time from the search input event to the result-count mutation with `performance.now()` and a `MutationObserver`. For load samples, read the Navigation Timing entry after load; count DOM elements and Resource Timing entries separately. The temporary benchmark script is not a publication input.

### Browser and automated checks

- Desktop and mobile layouts inspected; mobile document width equals its scroll width. Lookup controls stack below fields. Invalid IDs show an inline explanation, and Tab moves from the ID field to its adjacent lookup.
- Existing-model selection, preserved values after switching change/move, operation-aware deep links, batch fields, validation and nine-model Nova search verified. GitLab short-draft title/Markdown prefill, unchanged long-draft destination and clipboard copy were also checked in the local browser fixture. No provider form was submitted.
- Screenshots: [home](../img/modelo-home.png), [catalogue](../img/modelo-catalogue.png), [mobile proposal validation](../img/modelo-proposal-mobile.png). These are synthetic previews, not approval or T10 evidence.
- Linux: all 76 affected tests passed after updating the catalogue introduction and synthetic-notice assertions. The earlier broader unit/contract/site run passed 406 tests; its only two failures were those obsolete page-copy assertions.
- Both JavaScript behavior checks pass. The offline source and wheel package builds pass with locked uv/Python.

GitLab 18.1 EE instance access has not been supplied, so authenticated native-form submission and default-template interaction cannot be certified locally. The [GitLab 18.1 source documentation](https://gitlab.com/gitlab-org/gitlab/-/blob/v18.1.0-ee/doc/user/project/issues/create_issues.md) documents the native issue route and description prefill. Deployment validation must check its default-template append behavior. Trusted CI for the final PR head remains the acceptance arbiter.

### GitHub native-form follow-up

The user reported a missing title and unselected dropdowns. Live testing in the
actual GitHub issue form confirmed that an explicit `title` prefilled correctly,
and text fields prefilled after hydration, while dropdowns ended at `None` with
both option-name and index parameters. Even the fixed operation default did not
survive hydration reliably. A correct encoded URL alone had not proved this
native-form behavior; the original verification was insufficient here.

The URL builder now sends an explicit, bounded title for both providers. The
five GitHub templates retain their field IDs and parser headings, but prescribed
choices use text inputs with defaults and allowed values in their guidance.
Modelo retains dropdowns; the selected values pass through the supported native
text-prefill mechanism. Enum validation remains in the trusted compiler.
Controller tests cover value retention, invalid-draft blocking, clipboard denial
and missing clipboard support, in addition to provider URLs and the exact URL
limit. GitHub serves templates from the default branch, so the amended template
itself cannot be certified in the live native GUI before human review and merge.

GitHub documents [title and text-field URL prefills](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue#creating-an-issue-from-a-url-query)
and [text-input default values](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema#input).

### Request form and overview follow-up

The primary form now asks for an optional model/provider reference and a short
need. It creates a triage issue, not a MAC. The detailed composer remains
available. Both providers receive an explicit title. GitLab receives bounded
Markdown through its configured GUI route. The native form opens in a fresh tab.

The optional GitLab access button reads the configured repository GUI URL.
Tests cover 200, 403, other statuses, redirects, and failed requests. A 200 does
not assert login or issue-creation permission. In the browser, the reserved
invalid-host fixture reported that access could not be verified; the prepared
request link remained available. No live GitLab instance was configured.

The overview adds 5W+H, an ER diagram, review flow, file-key explanations, Git
review criteria, and artifact boundaries. Provider selectors are noncanonical;
internal model identities remain canonical within Modelo. The catalogue does
not hold `.pkl` files or weights. Embedded vertical-product AI is outside the
current component scope, not outside NIST risk management. Issue 78 tracks
external inventory integration.

Authored copy and diagram labels use concise, objective wording and sentence
case based on the Microsoft Writing Style Guide. Protocol field IDs and source
records retain their required spelling. Both diagrams have text alternatives.
At a 375-pixel document width, the overview had no page overflow; the 760-pixel
ER diagram scrolls inside its region. Desktop labels and connections were
visually inspected. The earlier performance samples describe the initial
redesign, before this additional prose and UI; they are not new measurements.

Review images: [simple request with GitLab access result](../img/modelo-request.jpg)
and [entity relationships and file keys](../img/modelo-entities.jpg).

Final local verification: 126 affected schema, contract, and site tests passed.
After the last wording and navigation edits, 45 targeted checks passed, including
SVG accessibility structure, native request templates, and the generated-site
link crawl. These sets overlap. Both JavaScript behavior checks and locked
offline source/wheel builds passed. The three baseline production governance
files remain absent; local `modelo check` is not a passing acceptance result.

### Agent handling, system assessment, and request detail

The agent quickstart and portable `modelo-maintain` skill cover triage, evidence
routing, maintenance, and handoff. Offering/record approval stays separate from
system NFR and API-contract assessment. The latter starts around 5-10 accepted
changes per day or a consumer contract requirement; it adds no record approval
steps and does not automatically add an API or database.

The final intake uses four short answers for vendor/model/link, business need,
intended use, and where/when. Optional choices cover rights-owner domicile,
operator, and processing territory. Unknowns stay blank; the agent verifies
selections. GitHub receives supported text prefills; GitLab receives marked
choice lists. The detailed MAC composer remains separate.

Shared navigation search uses the existing catalogue query. A browser search
for `nova` from the overview reached nine matching records. Clear comparison
resets selections and its URL parameters while retaining search and filters.

The generic skill-creator validator rejected the repository-required
`compatibility` frontmatter field. The native skill contract checks that field,
portable references, forbidden commands, and exclusion from the build/wheel;
those checks passed in the 49-check agent/navigation run. No validator was
weakened to hide the format difference.

The earlier exact-head CI run passed both protected-base and proposed-code
checks but failed the final gate because issue 76 was closed. The issue was
reopened for this ongoing work. Acceptance still requires a successful final
check at the next exact head.

Browser follow-up: keyboard Clear comparison removed both selected models while
retaining the `nova` query and nine results. Independent choices of USA domicile,
AWS operator, and UK processing survived the GitHub URL and Markdown handoff.
All groups began unticked. At 375 pixels, navigation and choice groups fit the
document width. [Request choices](../img/modelo-request-choices.jpg).

Latest verification: all 94 locked contract, proposal, template, and site tests
passed. After the final native-field wording and choice assertions, all 17
native-template tests passed. Both JavaScript checks passed, including the
comparison reset and independent request choice transport.
