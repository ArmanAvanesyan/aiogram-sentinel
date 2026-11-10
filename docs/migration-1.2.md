# Migrating to 1.2

Use a new PyPI version; do not overwrite the existing 1.1.0 distribution.
The public runtime version and distribution metadata now agree at 1.2.0.

- Handler policies now take effect through aiogram's registered callback metadata.
  Existing decorators that previously had no runtime effect may now enforce a
  stricter limit. Review both named and legacy policies before rollout.
- Explicit per-update policy values take precedence over handler/action defaults.
- Shared buckets and the existing 5/10-second global limit remain defaults.
  Split action-kind windows and exemptions require explicit application choices.
- Throttle/debounce windows and event counts must be positive bounded integers.
- Redis is optional: install `[redis]` when selecting it; base installs no longer
  require its client. Existing client injection uses the public `InfraBundle`.
- Hook updates preserve application and error middleware. Duplicate/attached router
  installation is rejected. Pass an unattached ancestor router to `setup`.
- Configure `ErrorConfig.reraise_exceptions` to preserve infrastructure failures;
  the empty default retains friendly handling. The webhook transport must also
  preserve the error and choose the retry status.
- The legacy `Sentinel.use_errors` convenience config is consumed by the next
  successful setup. Prefer explicit per-setup `error_config` for multiple bots.

Test the neutral [application example](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/examples)
and the [integration guide](application-integration.md) against the chosen wheel.
No application session, authorization, FSM store or business draft is owned by
Sentinel; do not substitute these spam-control scopes for conversation locks.
