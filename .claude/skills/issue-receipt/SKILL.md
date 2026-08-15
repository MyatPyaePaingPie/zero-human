---
name: issue-receipt
description: Post a decision or receipt comment on the owning GitHub issue (MyatPyaePaingPie/zero-human) and tick the epic #18 checklist. Use before building (decision) and after landing (receipt).
---
# issue-receipt
Decision comment (before): what you will build, the alternative you rejected, the falsifiable acceptance.
Receipt comment (after): commit sha(s) on main, test count green, what is deployed (or "not deployed,
wave N"), what is still open. Then edit #18's checklist line for the issue.

```
gh issue comment <n> --body "..."
gh issue view 18 --json body -q .body   # tick "- [ ] #n" -> "- [x] #n" via gh issue edit 18 --body-file
```
Keep receipts to five lines. Link files by repo path. No AI attribution.
