"""Where a playbook stands, what is ready to do next, and how to tick a box without touching anything else."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .model import Playbook, Task
from .parse import compile_playbook


def ready(book: Playbook, strict_order: bool = True) -> list[Task]:
    """Open tasks that can be started now: every blocker is done and, with ``strict_order``, every earlier step is done.
    A blocker that does not exist counts as not done, so a typo cannot unblock work."""
    done = {t.id for t in book.tasks() if t.done}
    out = []
    for step in book.steps:
        if strict_order and any(not t.done for s in book.steps if s.number < step.number for t in s.tasks):
            continue
        out += [t for t in step.tasks if not t.done and all(b in done for b in t.blocked_by)]
    return out


def report(book: Playbook, today: date | None = None, within_days: int = 7) -> dict[str, Any]:
    tasks = book.tasks()
    done = sum(t.done for t in tasks)
    owners: dict[str, dict[str, int]] = {}
    for t in tasks:
        if t.owner:
            o = owners.setdefault(t.owner, {"open": 0, "done": 0})
            o["done" if t.done else "open"] += 1
    ids_done = {t.id for t in tasks if t.done}
    return {
        "title": book.title, "done": done, "total": len(tasks), "percent": round(100 * done / len(tasks), 1) if tasks else 0.0,
        "steps": [{"number": s.number, "title": s.title, "status": s.status, "done": sum(t.done for t in s.tasks), "total": len(s.tasks)}
                  for s in book.steps],
        "overdue": [t.id for t in tasks if today and t.due and t.due < today and not t.done],
        "due_soon": [t.id for t in tasks if today and t.due and today <= t.due <= today + timedelta(days=within_days) and not t.done],
        "by_owner": owners,
        "unowned_open": [t.id for t in tasks if not t.done and t.owner is None],
        "blocked": [t.id for t in tasks if not t.done and any(b not in ids_done for b in t.blocked_by)],
        "ready": [t.id for t in ready(book)],
    }


def tick(text: str, task_id: str, done: bool = True) -> str:
    """Set one checklist item to done (or not done) and change nothing else in the file. Raises ``KeyError`` for an unknown id."""
    book = compile_playbook(text)
    task = book.task(task_id)
    lines = text.splitlines(keepends=True)
    mark = "x" if done else " "
    lines[task.line - 1] = re.sub(r"\[( |x|X)\]", f"[{mark}]", lines[task.line - 1], count=1)
    return "".join(lines)


def to_plan(book: Playbook) -> dict[str, Any]:
    """The playbook as an orchestra.dsl plan: steps in order, each depending on the one before, with approvals and risk carried over."""
    steps = []
    for i, s in enumerate(book.steps):
        item: dict[str, Any] = {"id": f"step-{s.number}"}
        if i:
            item["depends_on"] = [f"step-{book.steps[i - 1].number}"]
        if s.attrs.get("approval") == "true" or any(t.approval for t in s.tasks):
            item["approval"] = True
        if s.risk:
            item["risk"] = max(0, min(5, s.risk))
        owners = sorted({t.owner for t in s.tasks if t.owner})
        if owners:
            item["tags"] = [f"owner:{o}" for o in owners]
        steps.append(item)
    return {"name": book.title or "", "steps": steps}
