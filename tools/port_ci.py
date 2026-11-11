import copy
import pathlib

import yaml

root = pathlib.Path(__file__).resolve().parents[1]
target = root / ".github/workflows"
target.mkdir(parents=True, exist_ok=True)
# Preserve each proven CI matrix in a standalone staging directory. This deliberately
# prevents the workspace lock from hiding compatibility and optional-dependency errors.
for pkg in sorted((root / "packages").iterdir()):
    for source in (pkg / ".github/workflows").glob("*.yml"):
        data = yaml.safe_load(source.read_text())
        name = source.name
        if any(
            word in name
            for word in ["publish", "release", "docs", "dependabot", "label", "pr-management"]
        ):
            continue
        if "jobs" not in data:
            continue
        data["name"] = f"{pkg.name}: {data.get('name', source.stem)}"
        if isinstance(data.get("concurrency"), dict):
            data["concurrency"]["group"] = f"{pkg.name}-{source.stem}-" + data["concurrency"].get(
                "group", "${{ github.ref }}"
            )
        triggers = data.pop(True, data.pop("on", {}))
        paths = [
            f"packages/{pkg.name}/**",
            ".github/**",
            "tools/**",
            "tests/integration/**",
            "pyproject.toml",
            "uv.lock",
        ]
        if pkg.name in ["aiogram-nav", "aiogram-idle"]:
            paths.append("packages/aiogram-coordination/**")
        if pkg.name == "aiogram-idle":
            paths.append("packages/aiogram-nav/**")
        data["on"] = {
            "push": {"branches": ["main"]},
            "pull_request": {"paths": paths},
            "workflow_dispatch": {},
        }
        for job in data["jobs"].values():
            if "steps" not in job:
                continue
            steps = []
            for step in job["steps"]:
                step = copy.deepcopy(step)
                if step.get("uses", "").startswith("actions/checkout@"):
                    options = step.get("with", {})
                    if options.get("repository") == "ArmanAvanesyan/aiogram-nav":
                        steps.append(
                            {
                                "name": "Stage matching Nav native source",
                                "if": step.get("if", "success()"),
                                "run": 'cp -a "$GITHUB_WORKSPACE/monorepo-source/packages/aiogram-nav" "$GITHUB_WORKSPACE/nav-native-source"',
                                "working-directory": "${{ github.workspace }}",
                                "shell": "bash",
                            }
                        )
                        continue
                    destination = options.get("path", ".")
                    step["with"] = {
                        **options,
                        "path": "monorepo-source",
                        "persist-credentials": False,
                    }
                    step["with"].pop("ref", None)
                    steps.append(step)
                    dest = (
                        "${GITHUB_WORKSPACE}"
                        if destination == "."
                        else "${GITHUB_WORKSPACE}/" + destination
                    )
                    steps.append(
                        {
                            "name": "Stage isolated distribution checkout",
                            "working-directory": "${{ github.workspace }}",
                            "shell": "bash",
                            "run": f'mkdir -p "{dest}"\ncp -a "$GITHUB_WORKSPACE/monorepo-source/packages/{pkg.name}/." "{dest}/"',
                        }
                    )
                    continue
                if "run" in step:
                    step["run"] = (
                        step["run"]
                        .replace("ruff check .", "ruff check --extend-exclude monorepo-source .")
                        .replace(
                            "ruff format --check .",
                            "ruff format --check --extend-exclude monorepo-source .",
                        )
                    )
                steps.append(step)
                if "uv sync" in step.get("run", ""):
                    peers = []
                    if pkg.name in ["aiogram-idle", "aiogram-nav"]:
                        peers.append("aiogram-coordination")
                    if pkg.name == "aiogram-idle" and "--extra nav" in step["run"]:
                        peers.append("aiogram-nav")
                    if peers:
                        commands = []
                        for peer in peers:
                            commands.append(
                                f'uv build --wheel --no-sources --project "$GITHUB_WORKSPACE/monorepo-source/packages/{peer}" --out-dir "$RUNNER_TEMP/peer-wheels/{peer}"'
                            )
                            commands.append(
                                f'uv pip install --no-deps "$RUNNER_TEMP/peer-wheels/{peer}/"*.whl'
                            )
                        steps.append(
                            {
                                "name": "Install matching monorepo peer artifacts",
                                "run": "\n".join(commands),
                            }
                        )
            job["steps"] = steps
        (target / f"{pkg.name}-{name}").write_text(
            "# Generated by tools/port_ci.py; package originals remain preservation inputs.\n"
            + yaml.safe_dump(data, sort_keys=False, width=120)
        )
(root / "tools").mkdir(exist_ok=True)
(root / "tools/port_ci.py").write_text(
    pathlib.Path(__file__)
    .read_text()
    .replace(
        "root=pathlib.Path(__file__).resolve().parents[1]",
        "root=pathlib.Path(__file__).resolve().parents[1]",
    )
)
print("Ported", len(list(target.glob("*.yml"))), "CI workflows")
