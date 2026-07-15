"""de-eval CLI entrypoint.

Subcommands: lint | triggers | safety | e2e. Exit 0 pass / 1 fail / 2 usage
(ARCHITECTURE.md §Cross-component contracts item 6). Unknown subcommands or
bad flags exit 2 via argparse's own error path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from de_eval import lint as lint_mod
from de_eval import paths
from de_eval import safety as safety_mod
from de_eval import triggers as triggers_mod
from de_eval.report import write_report
from de_eval.yaml_io import UsageError, eprint, load_yaml


def _default_scope_service_catalog() -> str:
    data = load_yaml(paths.FIXTURE_INSTANCE_DIR / "instance.yaml") or {}
    catalog = ((data.get("scope") or {}).get("service_catalog")) or []
    return ",".join(catalog)


def _resolve_skill_dir(target: str | None, subcommand: str) -> Path:
    """Resolves the skill directory for lint/triggers/safety/e2e.

    Accepts an explicit path; falls back to cwd if it looks like a skill
    dir; falls back to the demo's single skill (skills/skills/ticket-review)
    for the common no-arg invocation shape used by e2e --dry-run.
    """
    if target:
        p = Path(target).resolve()
        if not p.is_dir():
            raise UsageError(f"{subcommand}: not a directory: {p}")
        return p
    cwd = Path.cwd()
    if (cwd / "SKILL.md").is_file():
        return cwd
    demo_default = cwd / "skills" / "skills" / "ticket-review"
    if (demo_default / "SKILL.md").is_file():
        return demo_default
    raise UsageError(
        f"{subcommand}: no skill directory given and none could be inferred "
        f"from cwd ({cwd}); pass one explicitly"
    )


def cmd_lint(args: argparse.Namespace) -> int:
    target = _resolve_skill_dir(args.target, "lint")
    if (target / "SKILL.md").is_file():
        result = lint_mod.lint_skill(target)
    else:
        result = lint_mod.lint_instance_coverage(target)
    write_report(
        Path(args.report) if args.report else None,
        {"subcommand": "lint", "target": str(target), "ok": result.ok, "errors": result.errors},
    )
    if result.ok:
        print(f"lint: PASS ({target})")
        return 0
    eprint(f"lint: FAIL ({target})")
    for e in result.errors:
        eprint(f"  - {e}")
    return 1


def cmd_triggers(args: argparse.Namespace) -> int:
    from de_eval.fixture_runtime import ensure_fixture_runtime

    skill_dir = _resolve_skill_dir(args.target, "triggers")
    runtime_dir = ensure_fixture_runtime(skill_dir, rebuild=args.rebuild_fixture)
    scope = _default_scope_service_catalog()
    report = triggers_mod.run_triggers(skill_dir, runtime_dir, scope, cases_glob=args.cases)

    write_report(
        Path(args.report) if args.report else None,
        {
            "subcommand": "triggers",
            "target": str(skill_dir),
            "pass_threshold": report.pass_threshold,
            "ratio": report.ratio,
            "ok": report.ok,
            "results": [r.__dict__ for r in report.results],
        },
    )
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.case_id} ({r.expected}, triggered={r.triggered})")
    print(f"triggers: {report.ratio:.2f} >= {report.pass_threshold} -> {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1


def cmd_safety(args: argparse.Namespace) -> int:
    from de_eval.fixture_runtime import ensure_fixture_runtime

    skill_dir = _resolve_skill_dir(args.target, "safety")
    runtime_dir = ensure_fixture_runtime(skill_dir, rebuild=args.rebuild_fixture)
    scope = _default_scope_service_catalog()
    report = safety_mod.run_safety(skill_dir, runtime_dir, scope, cases_glob=args.cases)

    write_report(
        Path(args.report) if args.report else None,
        {
            "subcommand": "safety",
            "target": str(skill_dir),
            "pass_threshold": report.pass_threshold,
            "ratio": report.ratio,
            "ok": report.ok,
            "results": [r.__dict__ for r in report.results],
        },
    )
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.case_id} (expected={r.expected_verdict}) -- {r.reason}")
    print(f"safety: {report.ratio:.2f} >= {report.pass_threshold} -> {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1


def cmd_e2e(args: argparse.Namespace) -> int:
    from de_eval import e2e as e2e_mod

    skill_dir = _resolve_skill_dir(args.target, "e2e")
    scope = _default_scope_service_catalog()
    report = e2e_mod.run_e2e(
        skill_dir,
        scope,
        cases_glob=args.cases,
        dry_run=args.dry_run,
        rebuild_fixture=args.rebuild_fixture,
    )

    write_report(
        Path(args.report) if args.report else None,
        {
            "subcommand": "e2e",
            "target": str(skill_dir),
            "dry_run": args.dry_run,
            "ok": report.ok,
            "cases": [c.__dict__ for c in report.cases],
        },
    )

    for c in report.cases:
        status = "PASS" if c.passed else "FAIL"
        print(f"[{status}] {c.case_id} (case={c.case}) run_dir={c.run_dir}")
        if args.dry_run:
            print(f"  shims: {', '.join(c.shim_names)}")
            print("  fixture prefixes:")
            for row in c.fixture_table:
                marker = " [fallback]" if row["is_fallback"] else ""
                print(f"    - step={row['step']!r} prefix={row['command_prefix']!r} "
                      f"exit_code={row['exit_code']}{marker}")
        for e in c.execution_errors:
            eprint(f"  execution: {e}")
        for e in c.semantic_errors:
            eprint(f"  semantic: {e}")

    print(f"e2e: {'PASS' if report.ok else 'FAIL'} ({len(report.cases)} case(s))")
    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="de-eval", description="Evaluation harness (docs/40-evaluation/eval-spec.md)")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    def add_common(p: argparse.ArgumentParser, with_dry_run: bool = False, with_rebuild: bool = False) -> None:
        p.add_argument("target", nargs="?", default=None, help="skill directory (defaults to cwd / demo skill)")
        p.add_argument("--cases", default=None, help="glob filter over case ids / mock filenames")
        p.add_argument("--report", default=None, help="write a JSON report to this path")
        if with_rebuild:
            p.add_argument("--rebuild-fixture", action="store_true", help="force-rebuild the fixture runtime")
        if with_dry_run:
            p.add_argument("--dry-run", action="store_true", help="build/wire everything, run no agent")

    p_lint = sub.add_parser("lint", help="static checks (frontmatter, required files, coverage table)")
    p_lint.add_argument("target", nargs="?", default=None, help="skill or instance directory")
    p_lint.add_argument("--report", default=None)
    p_lint.set_defaults(func=cmd_lint)

    p_triggers = sub.add_parser("triggers", help="routing checks against triggers.yaml")
    add_common(p_triggers, with_rebuild=True)
    p_triggers.set_defaults(func=cmd_triggers)

    p_safety = sub.add_parser("safety", help="guardrail checks against safety.yaml")
    add_common(p_safety, with_rebuild=True)
    p_safety.set_defaults(func=cmd_safety)

    p_e2e = sub.add_parser("e2e", help="command-replay + judge checks against tests/*.mock.yaml")
    add_common(p_e2e, with_dry_run=True, with_rebuild=True)
    p_e2e.set_defaults(func=cmd_e2e)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return args.func(args)
    except UsageError as e:
        eprint(f"error: {e}")
        return 2
    except Exception as e:  # noqa: BLE001 - surfaced to CLI as an operational failure
        eprint(f"error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
