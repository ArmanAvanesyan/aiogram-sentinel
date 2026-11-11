# Repository and historical link migration

The planned surviving repository is the original Sentinel repository, renamed to aiogram-kit.
GitHub's Sentinel repository redirects follow that identity. Do not recreate aiogram-sentinel.

The original aiogram-kit repository is retained as aiogram-kit-legacy. Reusing its former name
means old original-Kit issue and PR URLs must be mapped explicitly rather than trusted to redirect:

| Original Kit record | Retained historical record after cutover |
| --- | --- |
| `aiogram-kit/pull/1` | [Original Kit PR 1](https://github.com/ArmanAvanesyan/aiogram-kit-legacy/pull/1) |
| `aiogram-kit/pull/2` | [Original Kit PR 2](https://github.com/ArmanAvanesyan/aiogram-kit-legacy/pull/2) |
| `aiogram-kit/pull/3` | [Original Kit PR 3](https://github.com/ArmanAvanesyan/aiogram-kit-legacy/pull/3) |

Original Kit's historical [v0.0.1 release](https://github.com/ArmanAvanesyan/aiogram-kit-legacy/releases/tag/v0.0.1)
and its assets also remain in the legacy repository. For original Kit branch, tag, workflow-run
and source-file links, replace the repository segment with `aiogram-kit-legacy`; source commit IDs
also remain reachable through the imported histories in the monorepo.

These are planned destinations until the rename is complete. The current Sentinel issue and PR
numbers remain attached to its surviving repository identity. Cmds, Coordination, Nav and Idle
historical PRs and release assets remain in their original repositories after archival.

GitHub Pages sites do not inherit repository URL redirects. The unified Kit site includes package
source documentation. Historical site URLs require separate verification and migration notices.
The complete machine-readable identity and record inventory is under `reports/monorepo-migration/`.
