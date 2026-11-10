# Standalone library release verification

Verified 10 November 2026. All releases use tags and exact reviewed wheel/sdist
bytes, with checksum manifests and verification evidence attached to GitHub releases.

| Package | Version | Publish workflow | GitHub release |
| --- | --- | --- | --- |
| Sentinel | 1.2.0 | [42797158079](https://github.com/ArmanAvanesyan/aiogram-sentinel/actions/runs/42797158079) | [v1.2.0](https://github.com/ArmanAvanesyan/aiogram-sentinel/releases/tag/v1.2.0) |
| Cmds | 0.2.0 | [42796263349](https://github.com/ArmanAvanesyan/aiogram-cmds/actions/runs/42796263349) | [v0.2.0](https://github.com/ArmanAvanesyan/aiogram-cmds/releases/tag/v0.2.0) |
| Coordination | 0.1.0 | [42817944342](https://github.com/ArmanAvanesyan/aiogram-coordination/actions/runs/42817944342) | [v0.1.0](https://github.com/ArmanAvanesyan/aiogram-coordination/releases/tag/v0.1.0) |
| Nav | 0.2.0 | [42818873054](https://github.com/ArmanAvanesyan/aiogram-nav/actions/runs/42818873054) | [v0.2.0](https://github.com/ArmanAvanesyan/aiogram-nav/releases/tag/v0.2.0) |
| Idle | 0.2.0 | [42820645415](https://github.com/ArmanAvanesyan/aiogram-idle/actions/runs/42820645415) | [v0.2.0](https://github.com/ArmanAvanesyan/aiogram-idle/releases/tag/v0.2.0) |

## Verification

- Sentinel: 365 tests, 91.63% coverage; installed minimum/current profiles 352
  tests each, with real Redis 7/8. Published API probe passed.
- Cmds: 299 tests, 94.32%; minimum/current installed profiles 289 each. Published
  standalone API probe passed.
- Coordination: installed minimum/current artifacts 77 tests each, real Redis
  7/8 and coverage above 90%. Published base and Redis-extra probes passed without
  Nav, Idle or Kit.
- Nav: 382 real-Redis tests per minimum/current installed profile; standalone
  profiles 301 tests each with Redis cases skipped. Source coverage 86.38%.
  Final CI includes Python 3.10–3.14, minimum/current aiogram and Redis 7/8.
  Published base and Redis-extra probes passed with Idle absent.
- Idle: complete minimum/current registry-only profiles each passed 589 tests,
  current coverage 88.94%. Independent installed-wheel runtime probe 43 tests.
  Final CI covers standalone and optional combined integration, Redis 7/8,
  Python 3.10–3.14 and minimum/current aiogram. Published base install contains
  neither Nav nor Redis; optional extras resolve published Nav and Coordination.
  A fresh PyPI-only combined installation passed 25 focused atomic recovery,
  external-session, manual navigation, custom FSM and shutdown tests against Redis7.

All package checks include strict typing, Ruff, documentation and security checks.
Hashes from PyPI match each release manifest. Individual package reports describe
concurrency, lease loss, uncertain effects, callback ownership and FSM coverage.

## Migration boundary

Follow [the application guide](application-migration-guide.md). Authentication,
external sessions, business drafts and application deployment remain outside these
libraries. Explicit storage activation requires drained old writers and backups;
no application migration was performed here. Memory remains non-durable and
single-process. Events remain observational rather than a durable analytics outbox.
