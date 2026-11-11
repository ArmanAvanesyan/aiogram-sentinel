"""Optional navigation projection; importing idle core never imports this module."""

try:
    import re

    import aiogram_nav

    if re.match(r"^0\.3(?:\.|$)", aiogram_nav.__version__) is None:
        raise ImportError("Install aiogram-idle[nav] with aiogram-nav>=0.3.0,<0.4")
    from .integration import NavigationIntegration
    from .mapping import IdentityMapping
    from .policies import NodePolicies
except ModuleNotFoundError as error:
    if error.name == "aiogram_nav" or (error.name or "").startswith("aiogram_nav."):
        raise ImportError(
            "Install aiogram-idle[nav] with a compatible aiogram-nav distribution"
        ) from error
    raise

__all__ = ["NavigationIntegration", "NodePolicies", "IdentityMapping"]
