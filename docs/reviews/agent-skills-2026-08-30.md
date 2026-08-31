# Addy Osmani Agent Skills review — 2026-08-30

## Source and decision

Reviewed [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills),
release [0.6.8](https://github.com/addyosmani/agent-skills/releases/tag/0.6.8),
annotated unsigned tag at
[`d2c37ef6225dd8726cdd369a8030307f48592d26`](https://github.com/addyosmani/agent-skills/tree/d2c37ef6225dd8726cdd369a8030307f48592d26),
28 August 2026, MIT.

Do not install the pack wholesale. Do not use any skill in the deterministic
build. T9 implements native Modelo workflows from Modelo's own contracts; no
upstream skill text is copied or closely adapted. Any future copied upstream
expression is a separate dependency and must record its exact URL, commit,
path, file SHA-256 and complete MIT notice inside that skill package.

## Format and trust

The 25 directories use the core open Agent Skills `SKILL.md` frontmatter and
progressive-disclosure shape and the repository has a native Codex plugin.
Claude commands, personas and hooks are adapters, not portable skills. The pack
has several reproducibility gaps: the README/plugin count still says 24 in
places; per-skill installation can omit shared references and the root licence;
optional `license`, `compatibility` and `allowed-tools` fields are absent; the
release has no checksum or provenance asset.

Natural-language skills are operational code from an agent's perspective.
Repository rules and platform permissions therefore override them. Hooks,
scripts, MCP dependencies and updates require separate review. No skill may
merge, self-approve, weaken CI or expand cloud access beyond read-only evidence.

The upstream structural checks passed at the pinned commit (25 skills and 25
reference checks; 136 routing checks), but reported 86% positive rank-one
routing. That is useful quality evidence, not deterministic enforcement.

## `npx`

`npx skills add addyosmani/agent-skills` is rejected for Modelo. It uses a
third-party installer, does not pin the installer in the documented command,
can resolve mutable upstream state and may copy or symlink into agent-specific
locations. Modelo CI and bootstrap use no `npx`.

Preferred process: inspect a pinned commit, assess methods, then write the
Modelo workflow natively from its own contract. Review the semantic diff like
code, statically validate structure and never auto-update. A pinned clone is
safer than `npx`, but remains outside the build. If upstream expression is ever
copied, its provenance and licence become package content as described above.

## Selection

| Influence | Skills | Modelo treatment |
|---|---|---|
| Strong | `source-driven-development`, `test-driven-development`, `debugging-and-error-recovery`, `code-review-and-quality`, `doubt-driven-development`, `incremental-implementation` | General methods fit; express them only through Modelo's native MAC, evidence and CI rules |
| Useful | `using-agent-skills`, `spec-driven-development`, `constraint-driven-development`, `planning-and-task-breakdown`, `context-engineering`, `api-and-interface-design`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `code-simplification`, `security-and-hardening`, `performance-optimization`, `deprecation-and-migration`, `documentation-and-adrs` | Consult methods; do not import service assumptions, duplicate contracts, arbitrary thresholds or mutable installs |
| Conflict-heavy | `git-workflow-and-versioning`, `ci-cd-and-automation`, `shipping-and-launch` | Do not import hard resets, direct pushes, service rollback or GitHub-only assumptions; Modelo owns MAC, protected main, neutral adapters and receipts |
| Not used in v0.1 | `idea-refine`, `interview-me`, `observability-and-instrumentation` | Direction is set; claimed confidence is not testable; no runtime service exists |

Notable upstream conflicts include advice to use `git reset --hard`, direct tag
pushes and direct revert/push rollback; mutable `npx -y` MCP setup; unpinned
npm/pipx/Homebrew tools; and a bundled skill script that writes `docs/ideas/`.
Modelo-native workflows must not introduce these behaviours.

## Boundary

```text
skill guides author/reviewer
  → proposed Git change
  → deterministic CI validates exact SHA
  → independent eligible reviewer may approve
```

CI never invokes an LLM or asks a skill whether the build is correct.
