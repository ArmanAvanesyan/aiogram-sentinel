# Review evidence and generated reports

Keep maintained review notes here, including their scope, commands and limitations.
Generated Bandit, pip-audit, coverage and benchmark output is ignored by Git.
The CI security job uploads `bandit-report.json` and `pip-audit-report.json` as
run-specific artifacts even when a scan fails; stale reports are not evidence
about the current source or dependency graph.

To reproduce security reports locally:

```bash
uv sync --frozen --all-extras
uv run --no-sync bandit -r src -c pyproject.toml -f json -o bandit-report.json
uv run --no-sync pip-audit --format json --output pip-audit-report.json
```

Both commands return nonzero for findings or scan errors. Review the reports
and fix or explicitly assess findings before merging; CI does not ignore them.
