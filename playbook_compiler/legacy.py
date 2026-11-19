"""The original dict-based API, kept as it was so existing callers keep working."""
from __future__ import annotations

from typing import Any

from .parse import compile_playbook


def parse(text: str) -> dict[str, Any]:
    book = compile_playbook(text)
    steps = [{"number": s.number, "title": s.title, "tasks": [{"text": t.raw, "done": t.done} for t in s.tasks if t.raw],
              "notes": [n for _l, n in s.notes]} for s in book.steps]
    return {"title": book.title, "meta": book.meta, "steps": steps}


def lint(playbook: dict[str, Any]) -> list[str]:
    issues = []
    if not playbook["title"]:
        issues.append("missing title (a single '# Title' line)")
    for key in ("owner", "version"):
        if key not in playbook["meta"]:
            issues.append(f"missing front matter: {key}")
    steps = playbook["steps"]
    if not steps:
        issues.append("no steps found")
    for expected, step in enumerate(steps, start=1):
        if step["number"] != expected:
            issues.append(f"step numbering: expected {expected}, found {step['number']}")
        if not step["tasks"]:
            issues.append(f"step {step['number']} has no checklist items")
        if any(not t["text"] for t in step["tasks"]):
            issues.append(f"step {step['number']} has an empty checklist item")
    return issues


def progress(playbook: dict[str, Any]) -> tuple[int, int]:
    """(done, total) across every checklist item."""
    tasks = [t for s in playbook["steps"] for t in s["tasks"]]
    return sum(t["done"] for t in tasks), len(tasks)
