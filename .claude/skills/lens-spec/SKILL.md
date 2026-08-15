---
name: lens-spec
description: Spec a lens for the Full Reality Check rubric (reality_check/lenses.py) as binary claims with mode, human flag, probe ids, personas, and stamp weight. Use when adding or revising a lens under issues #2, #7-#15.
---
# lens-spec
A lens is a question and 3-6 binary claims. For each claim decide:
- **mode**: `objective` (a probe id decides; zero model calls; prefer this whenever a URL check exists),
  `model` (batched persona call; only where judgment is the product), `both`.
- **human**: does a real person get asked this? Only for claims a stranger can answer from the page.
- **check**: for objective claims, the finding id prefixes (site-spec audit ids verbatim, lens-prefixed).
- **fix + owner**: the sentence the agent doc will show and whether an agent or a human owns it.
Then: personas (2-4), `human_question` (one sentence, yes/no + one line), `weight` (3 = can turn the
stamp red alone; only clarity/demand/viability/security).
Post the spec on the lens's issue before code; the code session wires it into `LENSES`.
