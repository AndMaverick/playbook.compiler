# playbook.compiler

An operating playbook that nobody can check is a document. One that parses, lints, and reports progress is part of the system. playbook.compiler turns a markdown playbook into structured data, flags structural problems, and counts what is done. Standard library only.

## Use

```python
from playbook_compiler import lint, parse, progress

book = parse(open("model-rollout.md").read())

lint(book)       # [] when the playbook is complete and well formed
progress(book)   # (1, 3): one of three checklist items done
```

A playbook is plain markdown with front matter, a title, numbered steps, and checklists:

```
---
owner: Platform AI
version: 1.2
---
# Model rollout

## Step 1: Evaluate
- [x] Baseline recorded
- [ ] Regression gate green
```

## What the linter enforces

- A title, an owner, and a version, so every playbook has an accountable human and a revision.
- Steps numbered from 1 with no gaps.
- At least one checklist item per step, none of them empty.

Run it in CI and a playbook that drifts out of shape fails the build.

## Tests

```
python -m unittest discover -s tests -t . -v
```

MIT licensed. Built by [AndMaverick LLC](https://www.andmaverick.com).

---

**If this is your problem.** If you are deciding what to build, buy, and fund, I help leadership teams make that call with evidence. [Begin a conversation](https://calendly.com/andmaverick?utm_source=github&utm_medium=repo&utm_campaign=playbook.compiler).
