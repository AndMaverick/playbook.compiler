"""playbook.compiler: treat an operating playbook as something that can be checked, tracked and handed to a system.

Markdown in, typed steps and tasks out, with line numbers. Lint for structure, governance (owners, approvals,
rollback for risky steps), staleness, dangling references and blocking cycles. Report progress, owners, overdue and
ready work. Tick a box without disturbing the rest of the file. Export the playbook as an orchestra.dsl plan.
"""
from __future__ import annotations

from .check import Config, Finding, check
from .legacy import lint, parse, progress
from .model import Playbook, Step, Task
from .parse import compile_playbook
from .report import ready, report, tick, to_plan

__version__ = "0.2.0"

__all__ = [
    "Playbook", "Step", "Task", "Config", "Finding", "compile_playbook", "check", "report", "ready", "tick", "to_plan",
    "parse", "lint", "progress", "__version__",
]
