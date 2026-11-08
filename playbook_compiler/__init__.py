"""playbook.compiler: turn markdown orchestration playbooks into structured data, and lint them."""

from __future__ import annotations

import re

__version__ = "0.1.0"

STEP = re.compile(r"^##\s+Step\s+(\d+):\s*(.+?)\s*$")
TASK = re.compile(r"^[-*]\s+\[( |x|X)\]\s+(.*)$")


def _front_matter(lines: list):
    if not lines or lines[0].strip() != "---":
        return {}, lines
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            meta = {}
            for raw in lines[1:index]:
                if ":" in raw:
                    key, value = raw.split(":", 1)
                    meta[key.strip().lower()] = value.strip()
            return meta, lines[index + 1:]
    return {}, lines


def parse(text: str) -> dict:
    meta, body = _front_matter(text.splitlines())
    title = None
    steps: list = []
    current = None
    for raw in body:
        line = raw.strip()
        if title is None and line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            continue
        step = STEP.match(line)
        if step:
            current = {"number": int(step.group(1)), "title": step.group(2), "tasks": [], "notes": []}
            steps.append(current)
            continue
        if current is None or not line:
            continue
        task = TASK.match(line)
        if task:
            current["tasks"].append({"text": task.group(2).strip(), "done": task.group(1) != " "})
        else:
            current["notes"].append(line)
    return {"title": title, "meta": meta, "steps": steps}


def lint(playbook: dict) -> list:
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


def progress(playbook: dict) -> tuple:
    """(done, total) across every checklist item."""
    tasks = [t for s in playbook["steps"] for t in s["tasks"]]
    return sum(t["done"] for t in tasks), len(tasks)
