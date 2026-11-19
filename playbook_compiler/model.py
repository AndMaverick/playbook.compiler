"""The compiled playbook: typed steps and tasks that remember where in the file they came from."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Task:
    id: str  # "2.3": the third checklist item of step 2, counting nested items in document order
    raw: str  # the text exactly as written, inline tags included
    text: str  # the text with @owner, due: and blocked-by: tags removed
    done: bool
    line: int  # 1-based line in the source
    depth: int = 0  # nesting level (two spaces or one tab per level)
    parent: str | None = None
    owner: str | None = None
    due: date | None = None
    blocked_by: tuple[str, ...] = ()
    approval: bool = False


@dataclass
class Step:
    number: int
    title: str
    line: int
    attrs: dict[str, str] = field(default_factory=dict)  # from a trailing {risk=3 approval rollback} block
    tasks: list[Task] = field(default_factory=list)
    notes: list[tuple[int, str]] = field(default_factory=list)  # (line, text)

    @property
    def risk(self) -> int:
        try:
            return int(self.attrs.get("risk", 0))
        except ValueError:
            return 0

    @property
    def status(self) -> str:
        if not self.tasks:
            return "empty"
        done = sum(t.done for t in self.tasks)
        return "done" if done == len(self.tasks) else "not started" if done == 0 else "in progress"


@dataclass
class Playbook:
    title: str | None
    meta: dict[str, str]
    steps: list[Step]
    orphans: list[Task] = field(default_factory=list)  # checklist items before the first step
    problems: list[tuple[int, str, str]] = field(default_factory=list)  # (line, code, message) found while parsing
    title_line: int = 0

    def tasks(self) -> list[Task]:
        return [t for s in self.steps for t in s.tasks]

    def task(self, task_id: str) -> Task:
        for t in self.tasks():
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    def step(self, number: int) -> Step:
        for s in self.steps:
            if s.number == number:
                return s
        raise KeyError(number)
