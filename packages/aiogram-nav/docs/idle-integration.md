# Optional aiogram-idle integration

Navigation works without an inactivity framework. The optional adapter is
implemented in `aiogram_idle.integrations.nav`, supplied by aiogram-idle rather
than imported by aiogram-nav. Install the compatible distributions
explicitly; installing aiogram-nav alone installs neither aiogram-idle nor Redis.

In a bot environment, the optional idle extra selects compatible navigation:

```sh
pip install 'aiogram-idle[nav]==0.2.0'
# Select aiogram-idle[nav,redis] for the shared Redis backend.
```

The adapter supports aiogram-nav `>=0.2.0,<0.3`. Its public entry points are:

```python
from aiogram_idle.integrations.nav import NavigationIntegration, NodePolicies
from aiogram_nav import Navigation

integration = NavigationIntegration(
    idle=idle,
    registry=registry,
    policies=NodePolicies(default="none", overrides={"editor": "draft"}),
    adapters={"editor": application_flow_adapter},
)
navigation = Navigation(
    registry=registry,
    repository=integration.navigation_repository,
    presenter=screen_presenter,
)
integration.install(dispatcher, navigation=navigation)
```

This construction excerpt assumes application-created `idle`, `registry`,
presenter and flow adapter objects. Policy IDs such as `none` and `draft` must
exist in the idle policy registry; they are not reserved built-in names.

Use only the combined `integration.install` path before worker startup. Its
automatic mode places bindings before business routers; explicit manual mode
accepts the application-positioned bindings router. Do not additionally call the standalone `navigation.install` or
`idle.install`. The combined installer verifies shared coordination and FSM
mapping. The idle backend owns session/activity state and stores navigation as a
versioned component; accepted navigation/activity updates commit together there.
Using two independent standalone repositories does not provide that atomicity.

Application FSM writes and external databases remain application-owned and are
not part of the backend transaction. Unknown sends and business effects remain
explicit recovery evidence; they are not automatically replayed by this adapter.
Stop idle workers before closing shared FSM stores when managing shutdown yourself.

See the adapter's
[full guide](https://github.com/ArmanAvanesyan/aiogram-idle/blob/main/docs/navigation.md)
for policy inheritance, accepted activity, memory/Redis examples and recovery.
Its integration tests and optional typing profile live in aiogram-idle; ordinary
navigation tests and installation checks continue without that peer package.
