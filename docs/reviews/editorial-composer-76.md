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
- Existing-model selection, preserved values after switching change/move, batch fields, validation, a complete GitHub URL and nine-model Nova search verified. No provider form was submitted.
- Screenshots: [home](../img/modelo-home.png), [catalogue](../img/modelo-catalogue.png), [mobile proposal validation](../img/modelo-proposal-mobile.png). These are synthetic previews, not approval or T10 evidence.
- First Linux run: 406 passed; two old page-copy assertions failed. The assertions were updated to check the new catalogue introduction and the explicit synthetic/non-approval notice. Affected checks are being rerun.
- Both JavaScript behavior checks pass. The offline source and wheel package builds pass with locked uv/Python.

GitLab 18.1 EE instance access has not been supplied, so authenticated native-form submission and default-template interaction cannot be certified locally. The [GitLab 18.1 source documentation](https://gitlab.com/gitlab-org/gitlab/-/blob/v18.1.0-ee/doc/user/project/issues/create_issues.md) documents the native issue route and description prefill. Deployment validation must check its default-template append behavior. Trusted CI for the final PR head remains the acceptance arbiter.
