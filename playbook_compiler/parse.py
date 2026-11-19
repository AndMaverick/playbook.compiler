"""Markdown to a compiled playbook. A single pass over the lines that respects code fences and records line numbers."""
from __future__ import annotations

import re
from datetime import date

from .model import Playbook, Step, Task

STEP = re.compile(r"^##\s+Step\s+(\d+)\s*[:.\-]\s*(.+?)\s*$")
TASK = re.compile(r"^(\s*)[-*+]\s+\[( |x|X)\](?:\s+(.*))?$")
ATTR_BLOCK = re.compile(r"\s*\{([^{}]*)\}\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
OWNER = re.compile(r"(?:(?<=\s)|^)@([\w][\w.\-]*)")
DUE = re.compile(r"(?:(?<=\s)|^)due:(\S+)")
BLOCKED = re.compile(r"(?:(?<=\s)|^)(?:blocked-by|after):([\d.,]+)")
APPROVAL = re.compile(r"(?:(?<=\s)|^)!approval\b")
TOKENS = re.compile(r"(?:(?<=\s)|^)(?:@[\w][\w.\-]*|due:\S+|(?:blocked-by|after):[\d.,]+|!approval\b)")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _attrs(block: str) -> dict[str, str]:
    out = {}
    for token in block.replace(",", " ").split():
        key, _, value = token.partition("=")
        out[key.lower()] = value or "true"
    return out


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _task(line_no: int, indent: str, mark: str, rest: str, step_number: int, count: int, stack: list[tuple[int, str]],
          problems: list[tuple[int, str, str]]) -> Task:
    width = len(indent.replace("\t", "    "))
    depth = width // 2
    while stack and stack[-1][0] >= depth:
        stack.pop()
    parent = stack[-1][1] if stack else None
    task_id = f"{step_number}.{count}"
    stack.append((depth, task_id))
    owner = OWNER.search(rest)
    due_m = DUE.search(rest)
    due = None
    if due_m:
        due = _parse_date(due_m.group(1))
        if due is None:
            problems.append((line_no, "PB112", f"due date {due_m.group(1)!r} is not a valid YYYY-MM-DD date"))
    blocked: tuple[str, ...] = ()
    b = BLOCKED.search(rest)
    if b:
        blocked = tuple(x for x in b.group(1).split(",") if x)
    text = re.sub(r"\s{2,}", " ", TOKENS.sub("", rest)).strip()
    return Task(task_id, rest.strip(), text, mark != " ", line_no, depth, parent, owner.group(1) if owner else None, due, blocked,
                bool(APPROVAL.search(rest)))


def compile_playbook(text: str) -> Playbook:
    """Parse playbook markdown. Never raises on bad input: problems are recorded and ``check`` reports them with line numbers."""
    lines = text.splitlines()
    problems: list[tuple[int, str, str]] = []
    meta: dict[str, str] = {}
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            problems.append((1, "PB108", "front matter opens with --- but never closes"))
        else:
            for i in range(1, end):
                raw = lines[i]
                if ":" in raw and not raw.lstrip().startswith("#"):
                    key, value = raw.split(":", 1)
                    meta[key.strip().lower()] = _unquote(value)
                elif raw.strip() and not raw.lstrip().startswith("#"):
                    problems.append((i + 1, "PB111", f"front matter line is not 'key: value': {raw.strip()!r}"))
            start = end + 1
    title: str | None = None
    title_line = 0
    steps: list[Step] = []
    orphans: list[Task] = []
    current: Step | None = None
    stack: list[tuple[int, str]] = []
    count = 0
    fence: tuple[str, int] | None = None
    for index in range(start, len(lines)):
        raw = lines[index]
        line_no = index + 1
        fm = FENCE.match(raw)
        if fence is not None:
            if fm and fm.group(1) == fence[0]:
                fence = None
            continue
        if fm:
            fence = (fm.group(1), line_no)
            continue
        line = raw.strip()
        if title is None and line.startswith("# ") and not line.startswith("## "):
            title, title_line = line[2:].strip(), line_no
            continue
        sm = STEP.match(line)
        if sm:
            heading = sm.group(2)
            attrs: dict[str, str] = {}
            am = ATTR_BLOCK.search(heading)
            if am:
                attrs = _attrs(am.group(1))
                heading = heading[:am.start()].rstrip()
            current = Step(int(sm.group(1)), heading, line_no, attrs)
            steps.append(current)
            stack, count = [], 0
            continue
        if not line:
            continue
        tm = TASK.match(raw)
        if tm:
            count += 1
            task = _task(line_no, tm.group(1), tm.group(2), (tm.group(3) or "").strip(), current.number if current else 0, count, stack, problems)
            (current.tasks if current else orphans).append(task)
        elif current is not None:
            current.notes.append((line_no, line))
    if fence is not None:
        problems.append((fence[1], "PB108", "code fence is never closed, so everything after it was skipped"))
    return Playbook(title, meta, steps, orphans, problems, title_line)
