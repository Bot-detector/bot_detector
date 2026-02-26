#!/usr/bin/env python3

from pathlib import Path

import tomli_w
import tomllib

ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"
ROOT_PYPROJECT = ROOT / "pyproject.toml"


def collect_project_dependencies():
    deps = set()

    for project_dir in PROJECTS_DIR.iterdir():
        pyproject_path = project_dir / "pyproject.toml"

        if not pyproject_path.exists():
            continue

        print(f"Collecting dependencies from {pyproject_path}")
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)

        project_deps = data.get("project", {}).get("dependencies", [])
        deps.update(project_deps)

    return sorted(deps)


def update_root_pyproject(dependencies):
    with ROOT_PYPROJECT.open("rb") as f:
        root_data = tomllib.load(f)

    root_data.setdefault("project", {})
    root_data["project"]["dependencies"] = dependencies

    with ROOT_PYPROJECT.open("wb") as f:
        tomli_w.dump(root_data, f)


def main():
    deps = collect_project_dependencies()
    update_root_pyproject(deps)
    print(f"Updated root pyproject.toml with {len(deps)} dependencies.")


if __name__ == "__main__":
    main()
