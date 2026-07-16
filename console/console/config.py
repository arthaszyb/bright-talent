"""Console configuration: paths derived from --repo (the de-demo root)."""
from __future__ import annotations

import dataclasses
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Config:
    repo_root: Path
    port: int = 8900
    db_path: Path | None = None

    @property
    def instances_dir(self) -> Path:
        return self.repo_root / "instances"

    @property
    def scaffold_dir(self) -> Path:
        return self.repo_root / "scaffold"

    @property
    def skills_dir(self) -> Path:
        return self.repo_root / "skills"

    @property
    def de_cli(self) -> Path:
        return self.scaffold_dir / "de"

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path is not None:
            return self.db_path
        return Path(__file__).resolve().parent.parent / "data" / "console.db"

    @property
    def workspaces_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "workspaces"

    @classmethod
    def from_args(cls, repo: str, port: int = 8900, db_path: str | None = None) -> "Config":
        return cls(
            repo_root=Path(repo).resolve(),
            port=port,
            db_path=Path(db_path).resolve() if db_path else None,
        )
