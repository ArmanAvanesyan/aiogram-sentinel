# Changelog

<!-- towncrier release notes start -->

## 0.1.0 (2026-11-10)

### Features

- Add shared task-scoped memory coordination and renewable fenced Redis coordination without Idle/Nav/Kit dependencies.
- Normalize complete conversation identities losslessly while retaining existing canonical Redis lock hashes and caller-selected prefixes.
- Add explicit tracked application FSM isolation, custom lease-provider receipts and renewable Redis reference isolation.
- Revoke borrowed effect capabilities immediately when application FSM ownership is lost; preserve external cancellation and count queued scopes during shutdown.
- Expose read-only external-session authority with immutable absolute lifetime and separate inactivity expiry.
- Ship typed artifacts, standalone examples, compatibility CI and real-Redis concurrency/process-crash tests.
