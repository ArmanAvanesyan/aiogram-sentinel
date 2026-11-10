# Local verification

The review fixes retain this repository's src layout, Hatch build and existing
profile/configuration APIs. No release version was invented: version.py remains
the runtime authority and exports 0.1.1, matching project metadata.

Manager operations propagate original Telegram failures by default. The optional
best_effort flag returns False, including when a multi-scope update partially
completed. Success logging happens only after completion. Cancellation propagates.
The generic update_profile method accepts application-selected profile names;
legacy registration/vehicle flags remain compatible.

Verified locally on macOS:

- Ruff lint and formatting; strict Pyright over src with no diagnostics.
- Complete suite: 258 tests, including performance tests, with 97.22% statement coverage.
- Wheel and sdist builds and Twine metadata checks.
- Isolated installed wheel: 248 unit/integration tests on Python 3.12 / aiogram 3.31.0.
- Isolated installed sdist: 248 unit/integration tests on Python 3.10 / aiogram 3.0.0.
- Installed version equality, packaged py.typed and absence of Redis in base installs.
- Strict MkDocs build (existing informational relative-link notices remain).

CI now checks unit/integration coverage on advertised CPython 3.10–3.13 versions,
minimum/latest aiogram boundaries, and isolated installed artifacts. CI itself
was not run remotely. PyPy and cross-platform jobs remain CI responsibilities.
The Redis extra remains a client convenience, with no backend or distributed
coordination implementation promised. No changes were committed or published.
