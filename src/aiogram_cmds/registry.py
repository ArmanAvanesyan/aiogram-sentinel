"""
Command registry for managing profiles and commands in CmdsConfig.
"""

from .customize import CmdsConfig, CommandDef, ProfileDef


class CommandRegistry:
    def __init__(self, cfg: CmdsConfig) -> None:
        self.cfg = cfg

    def resolve_profile_commands(self, profile: str) -> list[str]:
        p: ProfileDef | None = self.cfg.profiles.get(profile)
        if not p:
            return []
        keep = [n for n in p.include if n in self.cfg.commands]
        exclude = set(p.exclude)
        return [n for n in keep if n not in exclude]

    def get_command(self, name: str) -> CommandDef | None:
        return self.cfg.commands.get(name)
