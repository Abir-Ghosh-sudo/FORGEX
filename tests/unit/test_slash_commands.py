
"""Unit tests for the FORGEX slash command system."""

import pytest

from forgex.cli.slash_commands import (
    SlashCommand,
    SlashCommandRegistry,
    create_builtin_registry,
)


@pytest.fixture
def registry() -> SlashCommandRegistry:
    """Create an empty command registry."""
    return SlashCommandRegistry()


def test_register_command(registry: SlashCommandRegistry) -> None:
    command = SlashCommand(
        name="hello",
        description="Test command.",
        handler=lambda: "hello",
    )

    registry.register(command)

    assert registry.get("hello") is command
    assert len(registry.commands) == 1


def test_register_alias(registry: SlashCommandRegistry) -> None:
    command = SlashCommand(
        name="hello",
        description="Test command.",
        handler=lambda: "hello",
        aliases=("hi", "h"),
    )

    registry.register(command)

    assert registry.get("hi") is command
    assert registry.get("h") is command


def test_duplicate_command_rejected(registry: SlashCommandRegistry) -> None:
    command = SlashCommand(
        name="hello",
        description="Test command.",
        handler=lambda: None,
    )

    registry.register(command)

    with pytest.raises(ValueError):
        registry.register(command)


def test_alias_collision_rejected(registry: SlashCommandRegistry) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="First command.",
            handler=lambda: None,
            aliases=("hi",),
        )
    )

    with pytest.raises(ValueError):
        registry.register(
            SlashCommand(
                name="other",
                description="Second command.",
                handler=lambda: None,
                aliases=("hi",),
            )
        )


def test_unregister_command(registry: SlashCommandRegistry) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="Test command.",
            handler=lambda: None,
            aliases=("hi",),
        )
    )

    assert registry.unregister("hello") is True
    assert registry.get("hello") is None
    assert registry.get("hi") is None


def test_unregister_using_alias(registry: SlashCommandRegistry) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="Test command.",
            handler=lambda: None,
            aliases=("hi",),
        )
    )

    assert registry.unregister("hi") is True
    assert registry.get("hello") is None


def test_parse_command(registry: SlashCommandRegistry) -> None:
    name, arguments = registry.parse('/run "fix login bug" --verbose')

    assert name == "run"
    assert arguments == ["fix login bug", "--verbose"]


def test_parse_command_without_arguments(
    registry: SlashCommandRegistry,
) -> None:
    name, arguments = registry.parse("/help")

    assert name == "help"
    assert arguments == []


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "/",
        "/   ",
        '/run "unfinished',
    ],
)
def test_parse_invalid_command(
    registry: SlashCommandRegistry,
    text: str,
) -> None:
    with pytest.raises(ValueError):
        registry.parse(text)


@pytest.mark.asyncio
async def test_dispatch_sync_handler(
    registry: SlashCommandRegistry,
) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="Test command.",
            handler=lambda: "success",
        )
    )

    result = await registry.dispatch("/hello")

    assert result.success is True
    assert result.command == "hello"
    assert result.data == "success"


@pytest.mark.asyncio
async def test_dispatch_async_handler(
    registry: SlashCommandRegistry,
) -> None:
    async def handler() -> str:
        return "async success"

    registry.register(
        SlashCommand(
            name="async",
            description="Async test command.",
            handler=handler,
        )
    )

    result = await registry.dispatch("/async")

    assert result.success is True
    assert result.data == "async success"


@pytest.mark.asyncio
async def test_dispatch_with_arguments(
    registry: SlashCommandRegistry,
) -> None:
    registry.register(
        SlashCommand(
            name="echo",
            description="Echo arguments.",
            handler=lambda *args: list(args),
        )
    )

    result = await registry.dispatch('/echo "hello world" test')

    assert result.success is True
    assert result.data == ["hello world", "test"]


@pytest.mark.asyncio
async def test_dispatch_using_alias(
    registry: SlashCommandRegistry,
) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="Test command.",
            handler=lambda: "works",
            aliases=("hi",),
        )
    )

    result = await registry.dispatch("/hi")

    assert result.success is True
    assert result.command == "hello"
    assert result.data == "works"


@pytest.mark.asyncio
async def test_dispatch_unknown_command(
    registry: SlashCommandRegistry,
) -> None:
    result = await registry.dispatch("/unknown")

    assert result.success is False
    assert result.command == "unknown"
    assert "Unknown command" in result.message


@pytest.mark.asyncio
async def test_dispatch_handler_error(
    registry: SlashCommandRegistry,
) -> None:
    def handler() -> None:
        raise RuntimeError("Something went wrong")

    registry.register(
        SlashCommand(
            name="fail",
            description="Failing command.",
            handler=handler,
        )
    )

    result = await registry.dispatch("/fail")

    assert result.success is False
    assert isinstance(result.error, RuntimeError)
    assert "Something went wrong" in result.message


def test_list_commands_by_category(
    registry: SlashCommandRegistry,
) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="General command.",
            handler=lambda: None,
            category="general",
        )
    )

    registry.register(
        SlashCommand(
            name="status",
            description="Session command.",
            handler=lambda: None,
            category="session",
        )
    )

    assert len(registry.list_commands("general")) == 1
    assert registry.list_commands("general")[0].name == "hello"


def test_help_text(registry: SlashCommandRegistry) -> None:
    registry.register(
        SlashCommand(
            name="hello",
            description="Say hello.",
            handler=lambda: None,
        )
    )

    help_text = registry.help_text()

    assert "FORGEX Slash Commands" in help_text
    assert "/hello" in help_text
    assert "Say hello." in help_text


def test_builtin_registry() -> None:
    registry = create_builtin_registry()

    expected_commands = {
        "help",
        "clear",
        "exit",
        "status",
        "model",
    }

    assert set(registry.commands) == expected_commands


@pytest.mark.asyncio
async def test_builtin_help_dispatch() -> None:
    registry = create_builtin_registry()

    result = await registry.dispatch("/help")

    assert result.success is True
    assert "FORGEX Slash Commands" in result.data


@pytest.mark.asyncio
async def test_builtin_clear_callback() -> None:
    called = False

    def clear_callback() -> None:
        nonlocal called
        called = True

    registry = create_builtin_registry()

    # Built-in callbacks receive their context through a handler.
    command = registry.get("clear")
    assert command is not None

    result = await command.handler({"clear_callback": clear_callback})

    assert result["action"] == "clear"
    assert called is True


@pytest.mark.asyncio
async def test_builtin_exit_callback() -> None:
    called = False

    def exit_callback() -> None:
        nonlocal called
        called = True

    registry = create_builtin_registry()
    command = registry.get("exit")

    assert command is not None

    result = await command.handler({"exit_callback": exit_callback})

    assert result["action"] == "exit"
    assert called is True
