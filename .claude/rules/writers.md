# One writer per surface
- `reality_check/`, `tests/`, `scripts/`, `render.yaml`, `run.sh`: zero-human (code) only.
- `docs/`, `.claude/`, `_meta/`: zero-human-brainstormer (advisor) only, except `_meta/chronicles`
  and `_meta/handoff.md` which either session appends to.
- Cross the line only with a comment on the issue naming the file and why. Subagents never commit.
