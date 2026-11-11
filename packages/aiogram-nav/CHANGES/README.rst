Changelog fragments
===================

Add a fragment for each user-facing change. Use an issue number or a leading
``+`` description when no issue exists: ``123.bugfix.rst`` or
``+repository-convention.doc.rst``. Supported types are ``feature``, ``bugfix``,
``doc``, ``removal`` and ``misc``. Describe the resulting behavior for users.

Preview without changing files with ``uv run --no-sync towncrier build --draft``.
Release maintainers build the changelog with an explicit version after reviewing
the draft; this removes consumed fragments. See ``docs/releasing.md``.
