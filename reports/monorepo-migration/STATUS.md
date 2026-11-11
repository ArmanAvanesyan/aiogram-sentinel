# Monorepo migration status

The surviving GitHub repository ID is `1065465593` (originally aiogram-sentinel).
The original Kit ID is `1424361052`; it is to become aiogram-kit-legacy.

## Preservation completed

- Verified Git bundles exist locally for all six original repositories.
- Original main histories are direct parents of the migration merge; no original commit IDs were rewritten.
- 92 historical refs have explicit source/object/destination mappings. Their remote preservation is pending the final cutover freeze.
- 68 GitHub release assets were downloaded and checked against size and available SHA256 metadata.
- All tracked and unignored working files have a local hash inventory. Kit's 16 working files were backed up and preserved; their hashes are committed here.
- GitHub API inventories include repository IDs, branches, labels, milestones, issues/PRs, releases, Pages, environments, workflows, permissions-related endpoints, secret names, project fields/items, comments and reviews. Unavailable endpoints are recorded, not assumed empty.
- Sentinel contains 41 ordinary issues. The other five repositories contain no ordinary issues in the captured inventory; their issue API records are historical PRs. A final delta check is required before cutover.
- The linked project is personal project 12, ID `PVT_kwHOBXlNW84BEMw1`. Its 41 items and 16 fields were inventoried. Preserve its identity and rename it during cutover.

Local backups are outside the repository at `../aiogram-migration-2026-11-11/`.
Raw configuration inventories are not committed because they can contain operational data.

## Verification completed

- All six wheel and sdist builds; all 12 Twine checks.
- All 12 artifacts installed in clean external environments without Redis. Idle had no Nav dependency and Nav had no Idle dependency.
- All five libraries passed strict Pyright checks using the workspace interpreter.
- Coordination with real Redis: 77 passed.
- Nav with real Redis: 439 passed, 13 optional native cases skipped.
- Idle with real Redis: 705 passed, 23 optional native cases skipped.
- Sentinel and Cmds Python suites passed; Sentinel real-Redis tests passed.
- Publishing verifier: 12 passed. Root Ruff, Actionlint and unified strict documentation build passed.

## Remaining gates

Full GitHub compatibility/native CI, clean native verification, final inventory delta,
remote history-ref preservation, repository renames, project/link mappings, publisher
configuration, independent patch releases, PyPI install verification and legacy notices.
No old repository may be archived until its gates pass. No migration release has been published yet.
