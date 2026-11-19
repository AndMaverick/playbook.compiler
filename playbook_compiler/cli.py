"""``python -m playbook_compiler``: lint, status, ready, tick and plan. Local only; ``tick`` is the only command that writes."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .check import Config, check
from .parse import compile_playbook
from .report import ready, report, tick, to_plan


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="playbook_compiler", description="Treat an operating playbook as something that can be checked.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lint = sub.add_parser("lint")
    lint.add_argument("files", nargs="+")
    lint.add_argument("--format", choices=["text", "json", "github"], default="text")
    lint.add_argument("--today", help="YYYY-MM-DD, default today; enables overdue and staleness checks")
    lint.add_argument("--max-age-days", type=int)
    lint.add_argument("--require-owners", action="store_true")
    lint.add_argument("--approval-risk", type=int, default=3)
    lint.add_argument("--semver", action="store_true")
    lint.add_argument("--strict", action="store_true", help="warnings fail too")
    for name in ("status", "ready", "plan"):
        sub.add_parser(name).add_argument("file")
    sub.choices["status"].add_argument("--today")
    t = sub.add_parser("tick")
    t.add_argument("file")
    t.add_argument("task")
    t.add_argument("--undo", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "tick":
            text = _read(args.file)
            new = tick(text, args.task, not args.undo)
            with open(args.file, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            print(f"{args.task} {'reopened' if args.undo else 'done'}")
            return 0
        if args.cmd == "lint":
            today = date.fromisoformat(args.today) if args.today else date.today()
            cfg = Config(require_owners=args.require_owners, today=today, max_age_days=args.max_age_days,
                         approval_risk=args.approval_risk, semver=args.semver)
            failed, results = False, {}
            for path in args.files:
                found = check(compile_playbook(_read(path)), cfg)
                results[path] = found
                failed |= any(f.severity == "error" or args.strict for f in found)
            if args.format == "json":
                json.dump({p: [vars(f) for f in fs] for p, fs in results.items()}, sys.stdout, indent=2)
                print()
            for path, fs in results.items():
                for f in fs:
                    if args.format == "github":
                        print(f"::{f.severity} file={path},line={f.line},title={f.code}::{f.message}")
                    elif args.format == "text":
                        print(f"{path}:{f}")
                if args.format == "text" and not fs:
                    print(f"{path}: ok")
            return 1 if failed else 0
        book = compile_playbook(_read(args.file))
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "status":
        today = date.fromisoformat(args.today) if args.today else date.today()
        r = report(book, today)
        print(f"{r['title']}: {r['done']}/{r['total']} done ({r['percent']}%)")
        for s in r["steps"]:
            print(f"  step {s['number']}: {s['title']:<30} {s['status']:<12} {s['done']}/{s['total']}")
        for key in ("overdue", "due_soon", "blocked", "unowned_open", "ready"):
            if r[key]:
                print(f"{key.replace('_', ' ')}: {', '.join(r[key])}")
    elif args.cmd == "ready":
        for task in ready(book):
            print(f"{task.id}  {task.text}" + (f"  @{task.owner}" if task.owner else ""))
    else:
        print(json.dumps(to_plan(book), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
