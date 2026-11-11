"""Port preserved package CI into isolated sibling staging directories."""

from __future__ import annotations

import copy
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / ".github/workflows"


def staged_path(value: str, destination: str) -> str:
    def one(line: str) -> str:
        if not line or line.startswith(("~", "/", "$", destination + "/")) or line == destination:
            return line
        if line.startswith("!"):
            return "!" + one(line[1:])
        return destination + "/" + line

    return "\n".join(one(line) for line in value.splitlines())


def port(package: pathlib.Path, source: pathlib.Path) -> dict:
    data = yaml.safe_load(source.read_text())
    original_triggers = data.pop(True, data.pop("on", {}))
    data["name"] = f"{package.name}: {data.get('name', source.stem)}"
    if isinstance(data.get("concurrency"), dict):
        data["concurrency"]["group"] = f"{package.name}-{source.stem}-" + data["concurrency"].get(
            "group", "${{ github.ref }}"
        )
    paths = [
        f"packages/{package.name}/**",
        ".github/**",
        "tools/**",
        "tests/integration/**",
        "pyproject.toml",
        "uv.lock",
    ]
    if package.name in ["aiogram-nav", "aiogram-idle"]:
        paths.append("packages/aiogram-coordination/**")
    if package.name == "aiogram-idle":
        paths.append("packages/aiogram-nav/**")
    data["on"] = {
        "push": {"branches": ["main"]},
        "pull_request": {"paths": paths},
        "workflow_dispatch": {},
    }
    original_triggers = original_triggers if isinstance(original_triggers, dict) else {}
    if "schedule" in original_triggers:
        data["on"]["schedule"] = original_triggers["schedule"]
    if "native" in source.stem:
        data["on"]["push"]["tags"] = [f"{package.name}-native-v*"]
    elif source.stem == "nav-integration":
        data["on"]["push"]["tags"] = [
            f"{name}-v*" for name in ["aiogram-coordination", "aiogram-nav", "aiogram-idle"]
        ]
    else:
        data["on"]["push"]["tags"] = [f"{package.name}-v*"]
    for job in data["jobs"].values():
        if "github.event_name == 'schedule'" in job.get("if", ""):
            job["if"] = "github.ref == 'refs/heads/main' || " + job["if"]
        original_steps = job.get("steps", [])
        primary = next(
            (
                step
                for step in original_steps
                if step.get("uses", "").startswith("actions/checkout@")
                and not step.get("with", {}).get("repository")
            ),
            None,
        )
        if primary is None:
            continue
        destination = primary.get("with", {}).get("path", "distribution")
        if destination == ".":
            destination = "distribution"
        defaults = job.setdefault("defaults", {}).setdefault("run", {})
        defaults["working-directory"] = destination
        steps = []
        for original in original_steps:
            step = copy.deepcopy(original)
            action = step.get("uses", "")
            if action.startswith("actions/checkout@"):
                options = step.get("with", {})
                if options.get("repository") == "ArmanAvanesyan/aiogram-nav":
                    steps.append(
                        {
                            "name": "Stage matching Nav native source",
                            "if": step.get("if", "success()"),
                            "working-directory": "${{ github.workspace }}",
                            "shell": "bash",
                            "run": 'cp -a "$GITHUB_WORKSPACE/monorepo-source/packages/aiogram-nav" "$GITHUB_WORKSPACE/nav-native-source"',
                        }
                    )
                    continue
                step["with"] = {**options, "path": "monorepo-source", "persist-credentials": False}
                step["with"].pop("ref", None)
                steps.append(step)
                steps.append(
                    {
                        "name": "Stage isolated distribution checkout",
                        "working-directory": "${{ github.workspace }}",
                        "shell": "bash",
                        "run": f'mkdir -p "$GITHUB_WORKSPACE/{destination}"\ncp -a "$GITHUB_WORKSPACE/monorepo-source/packages/{package.name}/." "$GITHUB_WORKSPACE/{destination}/"',
                    }
                )
                continue
            if "run" in step:
                step["run"] = step["run"].replace("uv run --frozen", "uv run --no-sync")
                step["run"] = re.sub(
                    r"\$(?:GITHUB_WORKSPACE|\{GITHUB_WORKSPACE\})(?!/"
                    + re.escape(destination)
                    + r'(?:/|["\s]|$))',
                    "$GITHUB_WORKSPACE/" + destination,
                    step["run"],
                )
                if "working-directory" in step:
                    step["working-directory"] = staged_path(step["working-directory"], destination)
            options = step.get("with", {})
            if (
                action.startswith(
                    ("actions/upload-artifact@", "actions/download-artifact@", "actions/cache@")
                )
                and "path" in options
            ):
                options["path"] = staged_path(options["path"], destination)
            if action.startswith("codecov/") and "files" in options:
                options["files"] = ",".join(
                    staged_path(value, destination) for value in options["files"].split(",")
                )
            if action.startswith("PyO3/maturin-action@"):
                options["working-directory"] = staged_path(
                    options.get("working-directory", destination), destination
                )
            if action.startswith("astral-sh/setup-uv@"):
                options["cache-dependency-glob"] = staged_path(
                    options.get("cache-dependency-glob", "uv.lock"), destination
                )
            if options:
                step["with"] = options
            steps.append(step)
            if "uv sync" in step.get("run", ""):
                peers = (
                    ["aiogram-coordination"]
                    if package.name in ["aiogram-idle", "aiogram-nav"]
                    else []
                )
                if package.name == "aiogram-idle" and "--extra nav" in step["run"]:
                    peers.append("aiogram-nav")
                if peers:
                    commands = []
                    for peer in peers:
                        commands.extend(
                            [
                                f'uv build --wheel --no-sources --project "$GITHUB_WORKSPACE/monorepo-source/packages/{peer}" --out-dir "$RUNNER_TEMP/peer-wheels/{peer}"',
                                f'uv pip install --no-deps "$RUNNER_TEMP/peer-wheels/{peer}/"*.whl',
                            ]
                        )
                    steps.append(
                        {
                            "name": "Install matching monorepo peer artifacts",
                            "run": "\n".join(commands),
                        }
                    )
        job["steps"] = steps
    return data


def main() -> None:
    count = 0
    for package in sorted((ROOT / "packages").iterdir()):
        for source in (package / ".github/workflows").glob("*.yml"):
            if package.name == "aiogram-kit" and source.stem == "optimization-tools":
                continue
            if any(
                word in source.name
                for word in ["publish", "release", "docs", "dependabot", "label", "pr-management"]
            ):
                continue
            if "jobs" not in yaml.safe_load(source.read_text()):
                continue
            data = port(package, source)
            (TARGET / f"{package.name}-{source.name}").write_text(
                "# Generated by tools/port_ci.py; originals remain preservation inputs.\n"
                + yaml.safe_dump(data, sort_keys=False, width=120)
            )
            count += 1
    print(f"Ported {count} isolated package verification workflows")


if __name__ == "__main__":
    main()
