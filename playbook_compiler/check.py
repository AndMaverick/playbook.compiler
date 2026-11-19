"""Checks on a compiled playbook. Every finding has a stable code and a line number, so CI can annotate the file."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from graphlib import CycleError, TopologicalSorter

from .model import Playbook

_SEMVER = re.compile(r"^\d+(\.\d+){0,2}([-+][\w.\-]+)?$")
_STEP_REF = re.compile(r"\bstep\s+(\d+)\b", re.I)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" or "warning"
    line: int
    message: str
    step: int | None = None
    task: str | None = None

    def __str__(self) -> str:
        return f"line {self.line}: {self.severity} {self.code}: {self.message}"


@dataclass(frozen=True)
class Config:
    require_meta: tuple[str, ...] = ("owner", "version")
    require_owners: bool = False  # every open task must name an @owner
    approval_risk: int = 3  # steps at or above this risk need an approval and a rollback
    today: date | None = None  # enables the overdue check
    max_age_days: int | None = None  # enables the staleness check on the `reviewed` date
    semver: bool = False  # version must look like 1, 1.2, 1.2.3 or 1.2.3-rc1


def check(book: Playbook, config: Config | None = None) -> list[Finding]:
    cfg = config or Config()
    out: list[Finding] = [Finding(code, "error" if code != "PB111" else "warning", line, msg) for line, code, msg in book.problems]
    if not book.title:
        out.append(Finding("PB101", "error", 1, "missing title (a single '# Title' line)"))
    for key in cfg.require_meta:
        if key not in book.meta:
            out.append(Finding("PB102", "error", 1, f"missing front matter: {key}"))
    if cfg.semver and "version" in book.meta and not _SEMVER.match(book.meta["version"]):
        out.append(Finding("PB113", "error", 1, f"version {book.meta['version']!r} is not a version number"))
    if not book.steps:
        out.append(Finding("PB103", "error", 1, "no steps found"))
    for task in book.orphans:
        out.append(Finding("PB110", "warning", task.line, "checklist item outside any step", None, task.id))
    seen_titles: dict[str, int] = {}
    numbers = {s.number for s in book.steps}
    ids = {t.id: t for t in book.tasks()}
    for expected, step in enumerate(book.steps, start=1):
        if step.number != expected:
            out.append(Finding("PB104", "error", step.line, f"step numbering: expected {expected}, found {step.number}", step.number))
        if not step.tasks:
            out.append(Finding("PB105", "error", step.line, f"step {step.number} has no checklist items", step.number))
        key = step.title.casefold()
        if key in seen_titles:
            out.append(Finding("PB107", "warning", step.line, f"step {step.number} repeats the title of the step on line {seen_titles[key]}", step.number))
        seen_titles.setdefault(key, step.line)
        texts: dict[str, str] = {}
        for t in step.tasks:
            if not t.raw:
                out.append(Finding("PB106", "error", t.line, f"step {step.number} has an empty checklist item", step.number, t.id))
                continue
            if t.text.casefold() in texts:
                out.append(Finding("PB501", "warning", t.line, f"{t.id} repeats {texts[t.text.casefold()]}", step.number, t.id))
            texts.setdefault(t.text.casefold(), t.id)
            if cfg.require_owners and not t.done and t.owner is None:
                out.append(Finding("PB201", "error", t.line, f"{t.id} is open and has no @owner", step.number, t.id))
            if t.approval and t.owner is None:
                out.append(Finding("PB202", "error", t.line, f"{t.id} is an approval and names no @approver", step.number, t.id))
            if cfg.today and t.due and t.due < cfg.today and not t.done:
                out.append(Finding("PB302", "warning", t.line, f"{t.id} was due {t.due.isoformat()} and is still open", step.number, t.id))
            for blocker in t.blocked_by:
                if blocker not in ids:
                    out.append(Finding("PB402", "error", t.line, f"{t.id} is blocked by {blocker}, which does not exist", step.number, t.id))
                elif ids[blocker].line > t.line and ids[blocker].id.split(".")[0] != t.id.split(".")[0]:
                    out.append(Finding("PB404", "warning", t.line, f"{t.id} is blocked by {blocker}, which comes in a later step", step.number, t.id))
        if step.risk >= cfg.approval_risk:
            has_approval = step.attrs.get("approval") == "true" or any(t.approval for t in step.tasks)
            if not has_approval:
                out.append(Finding("PB203", "error", step.line, f"step {step.number} has risk {step.risk} and no approval", step.number))
            has_rollback = step.attrs.get("rollback") == "true" or any(
                t.text.casefold().startswith("rollback") for t in step.tasks) or any(n.casefold().startswith("rollback") for _l, n in step.notes)
            if not has_rollback:
                out.append(Finding("PB204", "error", step.line, f"step {step.number} has risk {step.risk} and no rollback", step.number))
        for line_no, text in step.notes + [(t.line, t.raw) for t in step.tasks]:
            for ref in _STEP_REF.findall(text):
                if int(ref) not in numbers:
                    out.append(Finding("PB401", "error", line_no, f"refers to step {ref}, which does not exist", step.number))
    graph = {t.id: {b for b in t.blocked_by if b in ids} for t in book.tasks()}
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        cycle = exc.args[1] if len(exc.args) > 1 else []
        first = ids[cycle[0]] if cycle and cycle[0] in ids else None
        out.append(Finding("PB403", "error", first.line if first else 1, "blocked-by tags form a cycle: " + " -> ".join(cycle)))
    if cfg.max_age_days is not None and cfg.today is not None:
        reviewed = book.meta.get("reviewed")
        try:
            when = date.fromisoformat(reviewed) if reviewed else None
        except ValueError:
            when = None
        if when is None:
            out.append(Finding("PB301", "warning", 1, "no valid `reviewed: YYYY-MM-DD` date in the front matter"))
        elif cfg.today - when > timedelta(days=cfg.max_age_days):
            out.append(Finding("PB301", "warning", 1, f"last reviewed {when.isoformat()}, more than {cfg.max_age_days} days ago"))
    seen: set[tuple[str, int, str]] = set()
    unique = []
    for f in sorted(out, key=lambda f: (f.line, f.code)):
        if (f.code, f.line, f.message) not in seen:
            seen.add((f.code, f.line, f.message))
            unique.append(f)
    return unique
