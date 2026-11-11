"""aiogram-kit: reserved namespace for the aiogram-kit meta package.

The libraries live in their own packages for now:

- aiogram-sentinel: rate limiting, debouncing and error handling middleware
- aiogram-cmds: bot command management with i18n and per-user scopes
"""

from .version import __version__

__all__ = ["__version__"]
