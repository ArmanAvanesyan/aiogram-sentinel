# Public API

The typed `aiogram_idle` package exports the standalone contracts below. The
source annotations and protocol definitions specify complete signatures.

| Contract group | Principal API | Responsibility |
| --- | --- | --- |
| Runtime | `IdleRuntime`, `IdleContext` | Install middleware, manage workers, inspect state and explicitly accept activity |
| Configuration | `IdleConfig`, `ConfigManifest`, `ConfigUpdate`, `AmbiguousSendPolicy` | Creation, polling, limits, retained configuration and unknown delivery policy |
| Identity and guards | `IdleConversationKey`, `SessionGuard`, `ActivityGuard` | Actor-owned private conversation identity and conditional generations |
| Activity | `ActivitySpec`, `SessionSnapshot`, `ActivitySnapshot`, `RuntimeSnapshot` | Immutable session/activity/lifecycle views |
| Policies | `IdlePolicies`, `ExemptPolicy`, `PromptPolicy`, `QuietRestorePolicy` | Named idle behavior independent of navigation |
| Application effects | `FlowAdapter`, `FlowContext`, `FlowEligibility`, `ActionReceipt`, `EffectRecorder` | Eligibility, business effects and recoverable checkpoints |
| Presentation | `PromptPresenter`, `TelegramPromptPresenter`, `PromptTexts`, `QuietHoursResolver` | Localized questions, outcomes and quiet-hour delivery |
| Coordination and time | `Coordinator`, `MemoryCoordinator`, `AiogramMemoryCoordinator`, `Clock`, `ManualClock`, `SystemClock` | Shared handler/worker ownership and injectable clocks |
| Storage | `IdleBackend`, `MemoryIdleBackend` | Idle-owned sessions, activity, receipts, jobs and optional opaque components |

`IdleContext` exposes `open_session`, guarded `replace_session`, `current`, `enter`,
`touch` and `clear`. Use stable operation IDs for logical substeps. Retries return
retained receipts; different inputs with the same ID fail. See
[standalone integration](standalone.md) for acceptance and FSM rules.

Import `RedisIdleBackend` from `aiogram_idle.storage.redis` only when using the
`redis` extra. Import `NavigationIntegration` and `NodePolicies` from
`aiogram_idle.integrations.nav` only when using the `nav` extra. Neither optional
module is needed for core imports.

Errors derive from `IdleError`. Handle specific conflicts, expiry, ownership loss,
configuration/schema mismatch, overload, persistence unavailability and unknown
effect outcomes according to [recovery](recovery.md). A generic catch-and-continue
cannot safely authorize business work after persistence or coordination fails.
