"""Application-owned rendering and cleanup without a second message owner."""

from collections.abc import Awaitable, Callable

from ..errors import ConfigurationError
from ..models import RenderRequest, RenderResult
from .base import CleanupRequest, CleanupResult


class ApplicationPresenter:
    """Delegate effects to application callbacks; omitted rendering is tracking-only.

    Callbacks must use the request's effect recorder/ownership guard for each
    external operation. Replay safety is opt-in, just as for custom presenters.
    """

    def __init__(
        self,
        *,
        cleanup: Callable[[CleanupRequest], Awaitable[CleanupResult]],
        render: Callable[[RenderRequest], Awaitable[RenderResult]] | None = None,
        replay_safe: bool = False,
    ) -> None:
        if not callable(cleanup) or (render is not None and not callable(render)):
            raise ConfigurationError("Application presentation requires callable effects")
        if type(replay_safe) is not bool:
            raise ConfigurationError("replay_safe must be a boolean")
        self._cleanup, self._render = cleanup, render
        self.replay_safe = replay_safe
        self.automatic_rendering = render is not None

    async def render(self, request: RenderRequest) -> RenderResult:
        if self._render is None:
            raise ConfigurationError(
                "Application rendering requires prepare_action/complete_render"
            )
        return await self._render(request)

    async def cleanup(self, request: CleanupRequest) -> CleanupResult:
        if request.ensure_owned is not None:
            request.ensure_owned()
        return await self._cleanup(request)
