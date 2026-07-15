"""Materializes the skill-level fixture runtime (eval-spec.md §5.4 step 5).

Never re-implements the build: shells out to the real scaffold builder
(`uv run --project scaffold/builder python -m builder.build <instance_dir>`)
against the vendored `eval/fixture-instance/` config, exactly like `de build`
would for a real instance (ARCHITECTURE.md item 2). The skill-under-test is
then installed into `runtime/.claude/skills/<name>/` by a direct copy --
this is a deliberate demo simplification (no skills.yaml/registry pin) noted
in eval/README.md.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from de_eval import paths

_SKIP_DIR_NAMES = {".venv", "__pycache__", ".git", ".pytest_cache", "runs"}


class FixtureBuildError(Exception):
    pass


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    if not root.is_dir():
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.is_file():
            h.update(str(path.relative_to(root)).encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def _read_cache() -> dict:
    if paths.FIXTURE_CACHE_FILE.is_file():
        try:
            return json.loads(paths.FIXTURE_CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write_cache(data: dict) -> None:
    paths.FIXTURE_CACHE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_builder_build(instance_dir: Path) -> None:
    import os

    env = dict(os.environ)
    env["DE_SCAFFOLD_ROOT"] = str(paths.SCAFFOLD_ROOT)
    cmd = [
        "uv",
        "run",
        "--project",
        str(paths.BUILDER_PROJECT),
        "python",
        "-m",
        "builder.build",
        str(instance_dir),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FixtureBuildError(
            f"scaffold builder build failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )


def _install_skill(skill_dir: Path, runtime_dir: Path) -> None:
    dest = runtime_dir / ".claude" / "skills" / skill_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for src in skill_dir.rglob("*"):
        if any(part in _SKIP_DIR_NAMES for part in src.relative_to(skill_dir).parts):
            continue
        if src.is_file():
            rel = src.relative_to(skill_dir)
            dst_file = dest / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_file)


def ensure_fixture_runtime(skill_dir: Path, rebuild: bool = False, quiet: bool = False) -> Path:
    """Returns the path to the built + skill-installed fixture runtime/."""
    skill_dir = skill_dir.resolve()
    cache = _read_cache()
    skill_hash = _hash_tree(skill_dir)
    instance_hash = _hash_tree(paths.FIXTURE_INSTANCE_DIR / "instance.yaml")

    needs_build = (
        rebuild
        or not paths.FIXTURE_RUNTIME_DIR.is_dir()
        or cache.get("skill_name") != skill_dir.name
        or cache.get("skill_hash") != skill_hash
        or cache.get("instance_hash") != instance_hash
    )

    if needs_build:
        if not quiet:
            print(f"de-eval: building fixture runtime for skill '{skill_dir.name}'...", file=sys.stderr)
        _run_builder_build(paths.FIXTURE_INSTANCE_DIR)
        _install_skill(skill_dir, paths.FIXTURE_RUNTIME_DIR)
        _write_cache(
            {
                "skill_name": skill_dir.name,
                "skill_hash": skill_hash,
                "instance_hash": instance_hash,
            }
        )
    elif not quiet:
        print("de-eval: fixture runtime cache hit (use --rebuild-fixture to force)", file=sys.stderr)

    return paths.FIXTURE_RUNTIME_DIR
