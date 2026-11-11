"""Base prompt primitives for FORGEX agents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from string import Template
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """A single chat/message prompt item."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Renderable system/user prompt template for an agent role."""

    name: str
    system: str
    user: str
    required_variables: tuple[str, ...] = ()
    defaults: Mapping[str, Any] = field(default_factory=dict)

    def render(
        self,
        variables: Mapping[str, Any] | None = None,
    ) -> tuple[PromptMessage, PromptMessage]:
        values = dict(self.defaults)
        if variables:
            values.update(variables)

        missing = [
            key for key in self.required_variables if key not in values
        ]
        if missing:
            raise ValueError(
                f"Missing prompt variables for {self.name}: "
                + ", ".join(sorted(missing))
            )

        rendered: dict[str, str] = {}
        for key, value in values.items():
            if isinstance(value, (dict, list, tuple)):
                rendered[key] = _stringify(value)
            elif value is None:
                rendered[key] = ""
            else:
                rendered[key] = str(value)

        system = Template(self.system).safe_substitute(rendered).strip()
        user = Template(self.user).safe_substitute(rendered).strip()
        return (
            PromptMessage(role="system", content=system),
            PromptMessage(role="user", content=user),
        )


def render_prompt_messages(
    template: PromptTemplate,
    variables: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Render a template into serializable message dictionaries."""
    return [msg.to_dict() for msg in template.render(variables)]


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        parts = [f"{k}: {_stringify(v)}" for k, v in value.items()]
        return "{ " + ", ".join(parts) + " }"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_stringify(v) for v in value) + "]"
    return str(value)


__all__ = ["PromptMessage", "PromptTemplate", "render_prompt_messages"]
