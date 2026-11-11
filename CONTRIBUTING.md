# Contributing

Develop each distribution under `packages/<distribution>/`. Preserve its existing public imports,
optional dependencies, compatibility floor and recovery guarantees. Changes to shared coordination
must include Nav and Idle integration checks. Avoid unrelated runtime changes in packaging PRs.

## Workspace development

```sh
uv sync --frozen --all-packages --all-groups --all-extras --python 3.12
uv run --no-sync pytest tests/integration -q
uv run --no-sync mkdocs build --strict
```

Run package checks from the package directory so its own configuration and test imports apply:

```sh
cd packages/aiogram-nav
../../.venv/bin/python -m pytest
../../.venv/bin/pyright --pythonpath ../../.venv/bin/python
```

Follow the package's CI commands for lint, formatting, coverage and real-Redis profiles. The root
workspace lock supports joint development; isolated package locks keep minimum/latest compatibility
and standalone artifact verification independent. Do not weaken those checks to make a workspace pass.
Never configure application logging globally from library imports; examples may enable debug logging.

Package documentation is the source of truth and is included in the unified site through the docs hook.
Keep existing design documents and historical reports with their provenance. Add a package changelog
entry or change fragment for public behavior changes. See the package contributing guide for local details.

## Releases

Release distributions independently with `<distribution>-v<version>` tags. Build and independently test
wheel and sdist artifacts outside the workspace, then review their SHA256SUMS. Use the package-specific
publisher workflow with the reviewed manifest digest; it must publish those exact artifacts without rebuilding.

Native companions retain separate projects, platform matrices, artifact verification and measured
performance gates. Passing functional tests does not authorize a native release. Do not advertise
unpublished extras or make Rust, Redis, Nav or Idle dependencies mandatory for unrelated packages.

See `docs/monorepo.md` and `reports/monorepo-migration/` for migration procedures and outstanding gates.
