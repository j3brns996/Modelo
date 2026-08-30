# Contributing to Modelo

Every move, add, change, revoke or batch starts from a linked MAC issue. Work on
a topic branch, keep one writer per branch/worktree and submit a pull or merge
request. Review agents are read-only. Never write directly to protected `main`.

Before changing a path, read `AGENTS.md`, `modelo.yaml`, `docs/contract.yaml`
and its owning specification or schema. External catalogue facts require
admissible evidence; provider availability is not enterprise approval. Do not
add real catalogue records before the T10 launch gate passes.

Control-plane paths require a human CODEOWNER. A future independent eligible
agent may approve only allowlisted data paths, only after trusted CI succeeds
for the exact current head, and never if it authored, committed or modified the
change. A new commit invalidates that check and approval.

For T1, run:

```bash
uv sync --locked
uv run --locked python -m unittest discover -s tests/unit -v
uv run --locked modelo --version
uv run --locked modelo --help
```

Do not commit `dist/` or weaken a test to make a change pass. Technical debt is
permitted only with a linked issue that names an owner, rationale, removal
criterion, target release or date, and test reference.
