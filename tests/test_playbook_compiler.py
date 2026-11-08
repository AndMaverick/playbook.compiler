import unittest

from playbook_compiler import lint, parse, progress

GOOD = """---
owner: Platform AI
version: 1.2
---
# Model rollout

## Step 1: Evaluate
Run the offline suite first.
- [x] Baseline recorded
- [ ] Regression gate green

## Step 2: Approve
- [ ] Risk owner signs off
"""


class PlaybookTests(unittest.TestCase):
    def test_parse_structure(self):
        book = parse(GOOD)
        self.assertEqual(book["title"], "Model rollout")
        self.assertEqual(book["meta"], {"owner": "Platform AI", "version": "1.2"})
        self.assertEqual([s["title"] for s in book["steps"]], ["Evaluate", "Approve"])
        self.assertEqual(book["steps"][0]["notes"], ["Run the offline suite first."])
        self.assertEqual(book["steps"][0]["tasks"][0], {"text": "Baseline recorded", "done": True})

    def test_clean_playbook_has_no_issues(self):
        self.assertEqual(lint(parse(GOOD)), [])

    def test_progress(self):
        self.assertEqual(progress(parse(GOOD)), (1, 3))

    def test_lint_catches_structural_problems(self):
        bad = "# T\n\n## Step 2: Skipped one\n\n## Step 3: Empty\n"
        issues = lint(parse(bad))
        self.assertIn("missing front matter: owner", issues)
        self.assertTrue(any("expected 1, found 2" in i for i in issues))
        self.assertTrue(any("has no checklist items" in i for i in issues))

    def test_empty_document(self):
        issues = lint(parse(""))
        self.assertIn("no steps found", issues)
        self.assertTrue(any("missing title" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
