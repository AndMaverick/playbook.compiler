import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date

from playbook_compiler import Config, check, compile_playbook, ready, report, tick, to_plan
from playbook_compiler.cli import main

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(HERE, "examples", "model-rollout.md")
with open(EXAMPLE, encoding="utf-8") as fh:
    TEXT = fh.read()


def codes(text, **cfg):
    return [(f.code, f.line) for f in check(compile_playbook(text), Config(**cfg))]


class ParseTests(unittest.TestCase):
    def test_structure_and_line_numbers(self):
        b = compile_playbook(TEXT)
        self.assertEqual((b.title, b.title_line), ("Model rollout", 6))
        self.assertEqual(b.meta, {"owner": "Platform AI", "version": "1.2.0", "reviewed": "2026-09-01"})
        self.assertEqual([(s.number, s.title) for s in b.steps], [(1, "Evaluate"), (2, "Approve"), (3, "Ship")])
        self.assertEqual(b.step(1).attrs, {"risk": "1"})
        self.assertEqual(b.step(1).line, 10)
        self.assertEqual(TEXT.splitlines()[b.task("1.2").line - 1].strip()[:20], "- [ ] Regression gat")

    def test_inline_tags(self):
        t = compile_playbook(TEXT).task("1.2")
        self.assertEqual((t.owner, t.due, t.blocked_by, t.text), ("ana", date(2026, 10, 5), ("1.1",), "Regression gate green"))
        self.assertTrue(compile_playbook(TEXT).task("2.1").approval)

    def test_nesting(self):
        b = compile_playbook(TEXT)
        self.assertEqual((b.task("1.3").parent, b.task("1.3").depth, b.task("1.2").parent), ("1.2", 1, None))

    def test_code_fences_hide_their_contents(self):
        b = compile_playbook(TEXT)
        self.assertEqual([s.number for s in b.steps], [1, 2, 3])  # the "Step 9" inside the fence is not a step
        self.assertEqual(len(b.step(3).tasks), 3)

    def test_tags_need_a_word_boundary(self):
        t = compile_playbook("# T\n## Step 1: A\n- [ ] email ana@example.com about it\n").task("1.1")
        self.assertIsNone(t.owner)  # an email address is not an owner tag

    def test_tilde_fences_and_tab_indent(self):
        b = compile_playbook("# T\n## Step 1: A\n~~~\n- [ ] hidden\n~~~\n- [ ] a\n\t- [ ] b\n")
        self.assertEqual([t.id for t in b.tasks()], ["1.1", "1.2"])
        self.assertEqual(b.task("1.2").parent, "1.1")

    def test_never_raises_on_garbage(self):
        for junk in ("", "\x00\x01", "---", "---\n", "## Step x", "- [ ]", "```", "# \n## Step 1:\n", "a" * 10000, "\r\n\r\n"):
            compile_playbook(junk)
            check(compile_playbook(junk))


class CheckTests(unittest.TestCase):
    def test_example_is_clean_under_strict_governance(self):
        b = compile_playbook(TEXT)
        cfg = Config(require_owners=True, today=date(2026, 9, 15), max_age_days=90, semver=True)
        self.assertEqual([str(f) for f in check(b, cfg)], [])

    def test_structure_codes(self):
        self.assertEqual(codes(""), [("PB101", 1), ("PB102", 1), ("PB102", 1), ("PB103", 1)])
        found = codes("# T\n\n## Step 2: Skipped\n\n## Step 3: Empty\n- [ ]\n")
        self.assertIn(("PB104", 3), found)
        self.assertIn(("PB105", 3), found)
        self.assertIn(("PB106", 6), found)

    def test_unclosed_front_matter_and_fence_and_bad_front_matter_line(self):
        self.assertIn(("PB108", 1), codes("---\nowner: a\n# T\n"))
        self.assertIn(("PB108", 7), codes("---\nowner: a\nversion: 1\n---\n# T\n## Step 1: A\n```\n- [ ] x\n"))
        self.assertIn(("PB111", 2), codes("---\nthis is not a pair\n---\n# T\n"))

    def test_orphans_duplicates(self):
        found = codes("# T\n- [ ] stray\n## Step 1: Same\n- [ ] a\n- [ ] A\n## Step 2: same\n- [ ] b\n")
        self.assertIn(("PB110", 2), found)
        self.assertIn(("PB501", 5), found)
        self.assertIn(("PB107", 6), found)

    def test_owner_and_approver_rules(self):
        src = "# T\n## Step 1: A\n- [ ] do it\n- [x] done already\n- [ ] ok !approval\n"
        self.assertIn(("PB201", 3), codes(src, require_owners=True))
        self.assertNotIn(("PB201", 4), codes(src, require_owners=True))  # a finished task needs no owner
        self.assertIn(("PB202", 5), codes(src))

    def test_risky_steps_need_an_approval_and_a_rollback(self):
        found = codes("# T\n## Step 1: Wipe {risk=5}\n- [ ] go @a\n")
        self.assertIn(("PB203", 2), found)
        self.assertIn(("PB204", 2), found)
        gated = "# T\n## Step 1: Wipe {risk=5}\n- [ ] ok !approval @a\n- [ ] Rollback: restore snapshot @a\n"
        self.assertNotIn("PB203", [c for c, _ in codes(gated)])
        self.assertNotIn("PB204", [c for c, _ in codes(gated)])
        self.assertNotIn("PB204", [c for c, _ in codes("# T\n## Step 1: Wipe {risk=5 rollback}\n- [ ] x\n")])
        self.assertEqual([c for c, _ in codes("# T\n## Step 1: Read {risk=2}\n- [ ] x\n")], ["PB102", "PB102"])
        self.assertIn(("PB203", 2), codes("# T\n## Step 1: Mild {risk=2}\n- [ ] x\n", approval_risk=2))

    def test_dates_and_staleness(self):
        src = "---\nowner: a\nversion: 1\nreviewed: 2026-01-01\n---\n# T\n## Step 1: A\n- [ ] late due:2026-02-01\n- [ ] bad due:2026-13-45\n"
        found = codes(src, today=date(2026, 6, 1), max_age_days=90)
        self.assertIn(("PB302", 8), found)
        self.assertIn(("PB112", 9), found)
        self.assertIn(("PB301", 1), found)
        self.assertNotIn("PB301", [c for c, _ in codes(src, today=date(2026, 2, 1), max_age_days=90)])
        self.assertIn(("PB301", 1), codes(src.replace("reviewed: 2026-01-01\n", ""), today=date(2026, 6, 1), max_age_days=90))

    def test_references(self):
        src = "# T\n## Step 1: A\nSee step 4 for details.\n- [ ] b blocked-by:9.9\n- [ ] c blocked-by:2.1\n## Step 2: B\n- [ ] d\n"
        found = codes(src)
        self.assertIn(("PB401", 3), found)
        self.assertIn(("PB402", 4), found)
        self.assertIn(("PB404", 5), found)

    def test_blocking_cycles(self):
        found = codes("# T\n## Step 1: A\n- [ ] a blocked-by:1.2\n- [ ] b blocked-by:1.1\n")
        self.assertEqual([c for c, _ in found if c == "PB403"], ["PB403"])

    def test_version_format(self):
        self.assertIn(("PB113", 1), codes("---\nowner: a\nversion: banana\n---\n# T\n## Step 1: A\n- [ ] x\n", semver=True))
        self.assertNotIn("PB113", [c for c, _ in codes("---\nowner: a\nversion: 2.0.1-rc1\n---\n# T\n## Step 1: A\n- [ ] x\n", semver=True)])


class ReportTests(unittest.TestCase):
    def test_report(self):
        r = report(compile_playbook(TEXT), date(2026, 10, 3))
        self.assertEqual((r["done"], r["total"], r["percent"]), (1, 9, 11.1))
        self.assertEqual(r["overdue"], [])
        self.assertEqual(r["due_soon"], ["1.2"])
        self.assertEqual(r["by_owner"]["ana"], {"open": 2, "done": 1})
        self.assertEqual([s["status"] for s in r["steps"]], ["in progress", "not started", "not started"])
        self.assertEqual(report(compile_playbook(TEXT), date(2026, 11, 1))["overdue"], ["1.2"])

    def test_ready_respects_blockers_and_step_order(self):
        b = compile_playbook(TEXT)
        self.assertEqual([t.id for t in ready(b)], ["1.2", "1.3", "1.4"])  # step 2 and 3 wait for step 1
        self.assertEqual([t.id for t in ready(b, strict_order=False)][:3], ["1.2", "1.3", "1.4"])
        self.assertIn("2.1", [t.id for t in ready(b, strict_order=False)])
        self.assertNotIn("3.1", [t.id for t in ready(b, strict_order=False)])  # blocked by 2.1

    def test_a_typo_in_a_blocker_does_not_unblock_work(self):
        b = compile_playbook("# T\n## Step 1: A\n- [ ] x blocked-by:1.9\n")
        self.assertEqual(ready(b), [])


class TickTests(unittest.TestCase):
    def test_changes_one_character_and_nothing_else(self):
        new = tick(TEXT, "1.2")
        diff = [(a, b) for a, b in zip(TEXT.splitlines(), new.splitlines(), strict=True) if a != b]
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0][1], diff[0][0].replace("[ ]", "[x]", 1))
        self.assertEqual(len(new), len(TEXT))
        self.assertEqual(tick(new, "1.2", done=False), TEXT)  # and it undoes cleanly
        self.assertEqual(tick(new, "1.2"), new)  # idempotent

    def test_keeps_windows_line_endings(self):
        crlf = "# T\r\n## Step 1: A\r\n- [ ] a\r\n- [ ] b\r\n"
        self.assertEqual(tick(crlf, "1.2"), "# T\r\n## Step 1: A\r\n- [ ] a\r\n- [x] b\r\n")

    def test_unknown_task(self):
        with self.assertRaises(KeyError):
            tick(TEXT, "9.9")


class PlanExportTests(unittest.TestCase):
    def test_to_plan_is_a_valid_orchestra_plan_shape(self):
        plan = to_plan(compile_playbook(TEXT))
        self.assertEqual(plan["name"], "Model rollout")
        self.assertEqual([s["id"] for s in plan["steps"]], ["step-1", "step-2", "step-3"])
        self.assertEqual(plan["steps"][1], {"id": "step-2", "depends_on": ["step-1"], "approval": True, "risk": 2, "tags": ["owner:dmitri"]})
        allowed = {"id", "depends_on", "approval", "risk", "tags", "model", "cost", "latency"}
        self.assertTrue(all(set(s) <= allowed for s in plan["steps"]))
        json.dumps(plan)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_lint_text_json_github(self):
        code, out, _ = self.run_cli("lint", EXAMPLE, "--today", "2026-09-15", "--require-owners", "--semver", "--max-age-days", "90")
        self.assertEqual((code, out.strip().endswith("ok")), (0, True))
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.md")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("# T\n## Step 1: Wipe {risk=5}\n- [ ] go\n")
            code, out, _ = self.run_cli("lint", bad, "--format", "github")
            self.assertEqual(code, 1)
            self.assertIn(f"::error file={bad},line=2,title=PB203::", out)
            data = json.loads(self.run_cli("lint", bad, "--format", "json")[1])
            self.assertIn("PB204", [f["code"] for f in data[bad]])
            warn = os.path.join(d, "warn.md")
            with open(warn, "w", encoding="utf-8") as fh:
                fh.write("---\nowner: a\nversion: 1\n---\n# T\n- [ ] stray\n## Step 1: A\n- [ ] x\n")
            self.assertEqual(self.run_cli("lint", warn)[0], 0)  # a warning alone passes
            self.assertEqual(self.run_cli("lint", warn, "--strict")[0], 1)

    def test_status_ready_plan(self):
        code, out, _ = self.run_cli("status", EXAMPLE, "--today", "2026-10-03")
        self.assertEqual(code, 0)
        self.assertIn("1/9 done", out)
        self.assertIn("due soon: 1.2", out)
        self.assertIn("1.2  Regression gate green  @ana", self.run_cli("ready", EXAMPLE)[1])
        self.assertEqual(json.loads(self.run_cli("plan", EXAMPLE)[1])["steps"][0]["id"], "step-1")

    def test_tick_writes_only_the_one_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(TEXT)
            self.assertEqual(self.run_cli("tick", path, "1.2")[0], 0)
            with open(path, encoding="utf-8", newline="") as fh:
                self.assertEqual(fh.read(), tick(TEXT, "1.2"))
            self.assertEqual(self.run_cli("tick", path, "1.2", "--undo")[0], 0)
            with open(path, encoding="utf-8", newline="") as fh:
                self.assertEqual(fh.read(), TEXT)
            self.assertEqual(self.run_cli("tick", path, "9.9")[0], 2)
            self.assertEqual(self.run_cli("status", os.path.join(d, "missing.md"))[0], 2)


if __name__ == "__main__":
    unittest.main()
