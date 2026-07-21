"""Mock CI + MR providers (de-demo/DESIGN.md §S7, D4).

No network, no real Git hosting account. CI is a pure function of "does this
repo carry its managed CI entry point"; MRs are recorded as draft rows plus a
local git branch (never pushed anywhere).

Demo simplification (documented, see console/README.md): the demo's instance
trees don't carry a `.github/workflows/instance-ci.yml` (no such artifact is
produced anywhere in this fictional universe's build pipeline — see
DESIGN.md §S2). The instance-level "managed workflow file" the design doc's
demo note refers to is treated here as the instance's `Makefile`, which *is*
a committed, always-present managed file whose `verify` target
(`de validate && de build`) is the instance's actual local CI entry point.
The skills pipeline genuinely has a `skills-ci.yml` workflow (at the repo
root `.github/workflows/`, the only place GitHub executes workflows from),
so that one is checked literally per spec.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

CI_STEPS = ["validate", "build", "doctor", "status"]


class MockCIProvider:
    def instance_ci(self, instance_dir: Path) -> dict[str, Any]:
        marker = instance_dir / "Makefile"
        return self._status(marker.is_file())

    def skills_ci(self, skills_dir: Path) -> dict[str, Any]:
        # The workflow lives at the repository root .github/ (GitHub only
        # executes workflows from there); accept the legacy in-tree location
        # for skills registries that are standalone repos.
        markers = (
            skills_dir.parent / ".github" / "workflows" / "skills-ci.yml",
            skills_dir / ".github" / "workflows" / "skills-ci.yml",
        )
        return self._status(any(m.is_file() for m in markers))

    @staticmethod
    def _status(available: bool) -> dict[str, Any]:
        if not available:
            return {"available": False, "status": "unknown", "steps": []}
        return {
            "available": True,
            "status": "passing",
            "steps": [{"name": s, "status": "pass"} for s in CI_STEPS],
        }


class MockMRProvider:
    """Creating an MR = a local git branch on the console repo (the de-demo
    monorepo) named `console/draft-<id>`. Never pushes; never touches the
    instance's working tree (the branch just marks a point in the shared repo
    history — the draft's actual file changes live only in the isolated
    workspace + the draft row's stored diff/payload)."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def create_mr(self, draft_id: str, instance_id: str) -> dict[str, Any]:
        branch = f"console/draft-{draft_id}"
        subprocess.run(
            ["git", "-C", str(self.repo_root), "branch", branch],
            check=True,
            capture_output=True,
            text=True,
        )
        mr_iid = abs(hash(draft_id)) % 100000
        return {
            "mr_iid": mr_iid,
            "mr_url": f"mock://console-mr/{instance_id}/{mr_iid}",
            "branch": branch,
            "status": "open",
            "pipeline": {"status": "success", "steps": [{"name": s, "status": "pass"} for s in CI_STEPS]},
        }

    def close_mr(self, branch: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_root), "branch", "-D", branch],
            check=False,
            capture_output=True,
            text=True,
        )
