"""Tool registry/router: maps tool names to a primary tool and ordered fallbacks."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.base import Tool


@dataclass
class ToolRouter:
    primary: dict[str, Tool] = field(default_factory=dict)
    fallbacks: dict[str, list[Tool]] = field(default_factory=dict)

    def register(self, tool: Tool, *fallbacks: Tool) -> None:
        self.primary[tool.name] = tool
        self.fallbacks[tool.name] = list(fallbacks)

    def get(self, name: str) -> Tool:
        if name not in self.primary:
            raise KeyError(f"no tool registered for '{name}'")
        return self.primary[name]

    def get_fallbacks(self, name: str) -> list[Tool]:
        return self.fallbacks.get(name, [])

    def wrap(self, name: str, wrapper: type, *args: object, **kwargs: object) -> None:
        """Replace the primary tool with a wrapped version (used for fault injection)."""
        self.primary[name] = wrapper(self.get(name), *args, **kwargs)

    def names(self) -> list[str]:
        return list(self.primary)
