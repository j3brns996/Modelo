# CI efficiency review

Issue: [#103](https://github.com/j3brns996/Modelo/issues/103).

## Findings and decision

The shared verifier already splits the complete Python test inventory into at
most three processes. GitHub's protected-base and proposed-code jobs forced one
process. Pages used a separate serial test and package-build recipe.

Use the existing `modelo-local-ci verify --jobs 3` command in all three places.
Keep protected and proposed execution isolated, retain full test coverage and
offline package builds, and require every prerequisite to succeed. The quality
tests still execute Ruff, yamllint and the pinned UBS scanner.

This changes scheduling, not which changes qualify for acceptance. Do not reuse
an old successful check as acceptance of a new commit. Shared caches and
selective test skipping are outside this change.

## Measurement and validation

The successful [baseline run](https://github.com/j3brns996/Modelo/actions/runs/34080638846)
reported 458 tests in 530.58 seconds for protected code and 644.55 seconds for
proposed code. These are different hosted jobs, not a controlled benchmark.

The focused local checks passed: 17 runner/workflow tests, 21 documentation
tests, and strict yamllint on the changed workflows. Local full verification
uses pinned uv 0.11.33 and Python 3.12.13 on WSL Linux storage. An unrelated
test workload shares the host, so local elapsed time cannot establish a speedup
against hosted CI. The extra local serial measurement was stopped after 45
passing tests; it is not a successful full-suite baseline.

Full local verification passed: 458 tests across groups of 37, 30 and 391,
followed by the offline source and wheel builds. The groups reported 700.10,
539.78 and 802.91 seconds. Ruff, formatting, yamllint and the existing UBS gate
passed. UBS reported 28 critical findings under the existing scan policy; this
result does not mean the raw report has no findings.

The separate catalogue check failed on three governance files already absent
from the unchanged base: freshness.yaml, inference-services.yaml and vendors.yaml.
This maintenance change does not add production catalogue records.

## Developer workflow

Run affected tests first, then `uv run --locked modelo-local-ci verify --jobs 3`
before pushing. Use `--jobs 1` when memory is constrained. Full verification
includes the quality tests; a separate lint invocation is useful for quick
feedback but need not be repeated after a successful full run.

The changed paths are the trusted and Pages workflows, their contract tests,
and contributor guidance. No new dependency, tool version or acceptance cache
is introduced. Hosted runner contention may limit the benefit of parallelism;
successful remote runs will provide the operational timings.
