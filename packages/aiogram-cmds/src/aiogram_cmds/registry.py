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
        exclude = set(p.exclude)
        commands = self.cfg.commands
        return [n for n in p.include if n in commands and n not in exclude]

    def get_command(self, name: str) -> CommandDef | None:
        return self.cfg.commands.get(name)
