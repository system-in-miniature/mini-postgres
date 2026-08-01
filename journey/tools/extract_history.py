#!/usr/bin/env python3
"""Resolve MiniPostgres's history-driven Journey snapshots from Git evidence."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class StageSpec:
    number: int
    slug: str
    chapter: int
    source: str
    files: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoryManifest:
    name: str
    package: str
    repository_url: str
    base: str
    owned_roots: tuple[str, ...]
    owned_files: tuple[str, ...]
    excluded_files: tuple[str, ...]
    stages: tuple[StageSpec, ...]


def _strings(
    value: object, *, label: str, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise TypeError(f"{label} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"{label} must not be empty")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def git_file(root: Path, revision: str, path: str) -> bytes:
    try:
        return _git(root, "show", f"{revision}:{path}")
    except ValueError as error:
        raise ValueError(f"cannot read {revision}:{path}: {error}") from error


def _owned(
    path: str, roots: tuple[str, ...], files: tuple[str, ...], excluded: tuple[str, ...]
) -> bool:
    return path not in excluded and (
        path in files
        or any(path == root or path.startswith(root + "/") for root in roots)
    )


def _changed_files(
    root: Path,
    previous: str,
    source: str,
    owned_roots: tuple[str, ...],
    owned_files: tuple[str, ...],
    excluded_files: tuple[str, ...],
) -> tuple[str, ...]:
    paths = _git(root, "diff", "--name-only", previous, source).decode().splitlines()
    result = tuple(
        path for path in paths if _owned(path, owned_roots, owned_files, excluded_files)
    )
    if not result:
        raise ValueError(f"{previous}..{source} has no owned changes")
    return result


def load_manifest(path: Path) -> HistoryManifest:
    data = tomllib.loads(path.read_text())
    project = data.get("project")
    raw_stages = data.get("stages")
    if not isinstance(project, dict) or not isinstance(raw_stages, list):
        raise TypeError("manifest requires [project] and [[stages]]")
    root = path.parents[1]
    owned_roots = _strings(project.get("owned_roots"), label="owned_roots")
    owned_files = _strings(project.get("owned_files"), label="owned_files")
    excluded = _strings(
        project.get("excluded_files", []), label="excluded_files", allow_empty=True
    )
    base = str(project["base"])
    previous = base
    stages: list[StageSpec] = []
    for index, raw in enumerate(raw_stages, start=1):
        if not isinstance(raw, dict):
            raise TypeError(f"stage {index} must be a table")
        if raw.get("number") != index:
            raise ValueError(f"stage {index} has invalid number")
        source = str(raw["source"])
        files = _changed_files(
            root, previous, source, owned_roots, owned_files, excluded
        )
        candidate_tests = tuple(
            path
            for path in files
            if path.startswith("tests/") and Path(path).name.startswith("test_")
        )
        tests = (
            _strings(raw["tests"], label=f"stage {index} tests")
            if "tests" in raw
            else candidate_tests
        )
        if not set(tests) <= set(candidate_tests):
            raise ValueError(f"stage {index} focused tests must be changed test files")
        if not tests:
            raise ValueError(f"stage {index} requires focused tests")
        stages.append(
            StageSpec(
                number=index,
                slug=str(raw["slug"]),
                chapter=int(raw["chapter"]),
                source=source,
                files=files,
                tests=tests,
            )
        )
        previous = source
    return HistoryManifest(
        name=str(project["name"]),
        package=str(project["package"]),
        repository_url=str(project["repository_url"]),
        base=base,
        owned_roots=owned_roots,
        owned_files=owned_files,
        excluded_files=excluded,
        stages=tuple(stages),
    )


def snapshot_for_stage(
    manifest: HistoryManifest, number: int, *, root: Path
) -> dict[str, bytes]:
    if not 0 <= number <= len(manifest.stages):
        raise ValueError(f"stage number must be between 0 and {len(manifest.stages)}")
    snapshot: dict[str, bytes] = {}
    previous = manifest.base
    for stage in manifest.stages[:number]:
        deleted = _git(
            root,
            "diff",
            "--name-only",
            "--diff-filter=D",
            "--no-renames",
            previous,
            stage.source,
        ).decode().splitlines()
        for path in deleted:
            if _owned(
                path,
                manifest.owned_roots,
                manifest.owned_files,
                manifest.excluded_files,
            ):
                snapshot.pop(path, None)
        for path in stage.files:
            snapshot[path] = git_file(root, stage.source, path)
        previous = stage.source
    return snapshot


def owned_tree(root: Path, manifest: HistoryManifest) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for relative in manifest.owned_roots:
        base = root / relative
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            name = path.relative_to(root).as_posix()
            if (
                name in manifest.excluded_files
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
            ):
                continue
            result[name] = path.read_bytes()
    for relative in manifest.owned_files:
        result[relative] = (root / relative).read_bytes()
    return result


def _write_snapshot(directory: Path, snapshot: dict[str, bytes]) -> None:
    for child in directory.iterdir():
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for relative, payload in snapshot.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def patch_for_stage(manifest: HistoryManifest, number: int, *, root: Path) -> bytes:
    previous = snapshot_for_stage(manifest, number - 1, root=root)
    current = snapshot_for_stage(manifest, number, root=root)
    with tempfile.TemporaryDirectory(prefix=f"minipostgres-patch-{number:02d}-") as raw:
        repository = Path(raw)
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        _write_snapshot(repository, previous)
        subprocess.run(["git", "add", "-A"], cwd=repository, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=MiniPostgres Journey",
                "-c",
                "user.email=journey@example.invalid",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                f"stage-{number - 1:02d}",
            ],
            cwd=repository,
            check=True,
        )
        _write_snapshot(repository, current)
        subprocess.run(["git", "add", "-A"], cwd=repository, check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--binary", "--full-index", "--no-ext-diff"],
            cwd=repository,
            stdout=subprocess.PIPE,
            check=True,
        )
        if not result.stdout:
            raise ValueError(f"stage {number} generated an empty patch")
        return result.stdout


def write_stage_sources(
    manifest: HistoryManifest, *, root: Path, stages_root: Path
) -> None:
    stages_root.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    for stage in manifest.stages:
        name = f"{stage.number:02d}-{stage.slug}"
        expected.add(name)
        directory = stages_root / name
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath("stage.patch").write_bytes(
            patch_for_stage(manifest, stage.number, root=root)
        )
        directory.joinpath("tests.txt").write_text("\n".join(stage.tests) + "\n")
    for directory in stages_root.iterdir():
        if directory.is_dir() and directory.name not in expected:
            raise ValueError(f"unexpected Stage directory: {directory}")


def main() -> int:
    manifest = load_manifest(ROOT / "journey" / "manifest.toml")
    write_stage_sources(manifest, root=ROOT, stages_root=ROOT / "journey" / "stages")
    print(f"wrote {len(manifest.stages)} MiniPostgres Stage patch/test pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
