# Addy Osmani Agent Skills review — 2026-08-30

## Source and decision

Reviewed [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills),
release [0.6.8](https://github.com/addyosmani/agent-skills/releases/tag/0.6.8),
annotated unsigned tag at
[`d2c37ef6225dd8726cdd369a8030307f48592d26`](https://github.com/addyosmani/agent-skills/tree/d2c37ef6225dd8726cdd369a8030307f48592d26),
28 August 2026, MIT.

Do not install the pack wholesale. Do not use any skill in the deterministic
build. At T9, manually review and adapt a small pinned subset into canonical
`.agents/skills/`, recording upstream URL, commit, file SHA-256 and MIT notice.
CI must pass identically with no agent or skills installed.

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

`npx skills add addyosmani/agent-skills` is at most a human-controlled bootstrap
convenience. It uses a third-party installer, does not pin the installer in the
documented command, can resolve mutable upstream state and may copy/symlink into
agent-specific locations. It is invalid in Modelo CI.

Preferred process: inspect a pinned commit; select individual skills; adapt
them into `.agents/skills/`; retain attribution/provenance; review the semantic
diff like code; statically validate structure; never auto-update. A pinned clone
is safer than `npx`, but remains outside the build.

## Selection

| Decision | Skills | Modelo treatment |
|---|---|---|
| Adopt pinned | `source-driven-development`, `test-driven-development`, `debugging-and-error-recovery`, `code-review-and-quality`, `doubt-driven-development`, `incremental-implementation` | Strong direct fit; adapt only conflicting repository paths/commands |
| Adapt | `using-agent-skills`, `spec-driven-development`, `constraint-driven-development`, `planning-and-task-breakdown`, `context-engineering`, `api-and-interface-design`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `code-simplification`, `security-and-hardening`, `performance-optimization`, `deprecation-and-migration`, `documentation-and-adrs` | Keep useful methods; remove service assumptions, duplicate contracts, arbitrary thresholds and mutable installs |
| Adapt heavily | `git-workflow-and-versioning`, `ci-cd-and-automation`, `shipping-and-launch` | Remove hard resets/direct pushes, service rollback and GitHub-only assumptions; use MAC, protected main, neutral adapters and receipts |
| Reject for v0.1 | `idea-refine`, `interview-me`, `observability-and-instrumentation` | Direction is set; claimed confidence is not testable; no runtime service exists |

Notable upstream conflicts include advice to use `git reset --hard`, direct tag
pushes and direct revert/push rollback; mutable `npx -y` MCP setup; unpinned
npm/pipx/Homebrew tools; and a bundled skill script that writes `docs/ideas/`.
Modelo-specific adaptations must remove these behaviours.

## Boundary

```text
skill guides author/reviewer
  → proposed Git change
  → deterministic CI validates exact SHA
  → independent eligible reviewer may approve
```

CI never invokes an LLM or asks a skill whether the build is correct.

