# playbook.compiler

[![CI](https://github.com/AndMaverick/playbook.compiler/actions/workflows/ci.yml/badge.svg)](https://github.com/AndMaverick/playbook.compiler/actions/workflows/ci.yml)

An operating playbook that nobody can check is a document. One that parses, lints, reports progress and hands its structure to a system is part of the system. playbook.compiler turns a markdown playbook into typed steps and tasks with line numbers, checks it for the governance gaps that matter (no owner, no approver, a risky step with no gate and no rollback, a stale review), and tracks what is done and what can start next. Standard library only, typed, Python 3.10 and up.

```
pip install git+https://github.com/AndMaverick/playbook.compiler
```

## A playbook is still just markdown

```markdown
---
owner: Platform AI
version: 1.2.0
reviewed: 2026-09-01
---
# Model rollout

## Step 2: Approve {risk=2}
- [ ] Risk owner signs off !approval @dmitri
- [ ] Rollback plan reviewed @dmitri

## Step 3: Ship {risk=4}
- [ ] Canary at 5 percent for 24 hours @sam blocked-by:2.1 due:2026-10-05
- [ ] Ship approval !approval @dmitri
- [ ] Rollback: previous model id pinned @sam
```

Inline tags are optional and read like prose: `@owner`, `due:YYYY-MM-DD`, `blocked-by:2.1,2.3`, `!approval`. A trailing `{risk=4 rollback}` on a step heading sets its risk. Content inside code fences is never mistaken for structure, and nested checklists keep their parent.

See [`examples/model-rollout.md`](examples/model-rollout.md) for a complete one.

## Check it

```
$ python -m playbook_compiler lint playbook.md --require-owners --max-age-days 90
playbook.md:line 13: warning PB302: 1.2 was due 2026-10-05 and is still open
playbook.md:line 21: error PB203: step 3 has risk 4 and no approval
playbook.md:line 21: error PB204: step 3 has risk 4 and no rollback
```

Every finding has a stable code and a line number, and `--format github` prints GitHub Actions annotations so the problem shows up on the line in the pull request.

| Code | Meaning |
|---|---|
| PB101 to PB107 | Title, front matter, steps, numbering, empty steps, empty items, repeated titles |
| PB108, PB111, PB112 | Unclosed front matter or code fence, malformed front matter line, invalid date |
| PB110 | Checklist item outside any step |
| PB113 | Version is not a version number (`--semver`) |
| PB201 | Open task with no `@owner` (`--require-owners`) |
| PB202 | An approval that names no approver |
| PB203, PB204 | A step at or above the risk threshold with no approval, or no rollback |
| PB301, PB302 | Review date too old, or an overdue open task |
| PB401 to PB404 | Reference to a step that does not exist, blocker that does not exist, blocking cycle, blocker in a later step |
| PB501 | Duplicate task in a step |

`lint` exits 1 on errors (`--strict` includes warnings), so it works as a CI gate. Every finding is data too: `check(compile_playbook(text), Config(...))`.

## Track it

```
$ python -m playbook_compiler status playbook.md
Model rollout: 1/9 done (11.1%)
  step 1: Evaluate                       in progress  1/4
  step 2: Approve                        not started  0/2
  step 3: Ship                           not started  0/3
due soon: 1.2
blocked: 3.1
ready: 1.2, 1.3, 1.4

$ python -m playbook_compiler tick playbook.md 1.2
```

`ready` lists what can start now: every blocker is done and every earlier step is finished. A typo in a blocker never unblocks work. `tick` flips one checkbox and changes nothing else in the file, including line endings, so a bot or a script can keep a playbook current without reformatting a human's document.

## Hand it to a system

`to_plan(book)` exports the playbook as a plan for [orchestra.dsl](https://github.com/AndMaverick/orchestra.dsl): steps in order, approvals and risk carried over, owners as tags. The same governance question (is a risky step reachable without a human approval) can then be asked of the plan before it runs, and the plan's digest pinned. The tests check the export's shape, and it loads in orchestra.dsl as is.

## Compatibility

The original API (`parse`, `lint`, `progress` on plain dicts) is unchanged, and its tests still pass. New code should use `compile_playbook`, which keeps line numbers and typed fields.

## Honest limits

- It checks structure and declared governance. It cannot tell whether a named approver is the right person or whether a rollback step would actually work.
- Tags are conventions in prose. A playbook that never uses them passes the structural checks and fails the governance ones, which is the point.
- Dates are ISO only, and "today" is a parameter so results are reproducible.

## Tests

```
python -m unittest discover -s tests -t . -v
```

**Related repositories:** [orchestra.dsl](https://github.com/AndMaverick/orchestra.dsl) checks the plan a playbook exports. [mao-framework](https://github.com/AndMaverick/mao-framework) has a smaller module, `mao.playbook`, that compiles markdown runbooks into plans and audits their approval gates against the policy that will run.

MIT licensed. Built by [AndMaverick LLC](https://www.andmaverick.com).

---

**If this is your problem.** If you are deciding what to build, buy, and fund, I help leadership teams make that call with evidence. [Begin a conversation](https://calendly.com/andmaverick?utm_source=github&utm_medium=repo&utm_campaign=playbook.compiler).
