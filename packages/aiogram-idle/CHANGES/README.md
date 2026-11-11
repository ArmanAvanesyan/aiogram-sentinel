# Changelog fragments

Add a short reStructuredText fragment for a user-visible change. Name it
`<issue>.<type>.rst`, or `+<description>.<type>.rst` when no issue exists.
Supported types are `feature`, `bugfix`, `doc`, `removal` and `misc`.

Describe the resulting behavior for a library consumer. Keep internal details in
the pull request unless they explain a compatibility or recovery constraint.

Preview release notes without modifying files:

```sh
uv run --no-sync towncrier build --draft --version 0.1.0
```

Maintainers assemble the changelog as part of the documented release process;
adding a fragment does not publish or release the package.
