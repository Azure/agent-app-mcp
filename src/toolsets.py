"""Explicit, packaged toolset factories. No discovery or user-provided import paths."""

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from mcp.server import MCPServer

from shared.config import Configuration, Settings


class Toolset(Protocol):
    """Validated toolset whose dependencies live only for the server lifespan."""

    def lifespan(self, server: MCPServer, credential) -> AbstractAsyncContextManager[None]: ...


Factory = Callable[[Configuration], Toolset]
Loader = Callable[[], Factory]


def _load_nl2sql() -> Factory:
    from tools.nl2sql.runtime import configure

    return configure


REGISTRY: Mapping[str, Loader] = {"nl2sql": _load_nl2sql}


def prepare_toolsets(
    settings: Settings,
    configuration: Configuration,
    *,
    registry: Mapping[str, Loader] | None = None,
) -> list[Toolset]:
    """Reject the entire selection before importing or configuring any toolset."""
    registry = REGISTRY if registry is None else registry
    names = settings.MCP_TOOLSETS
    if len(names) != len(set(names)):
        raise ValueError("MCP_TOOLSETS must not contain duplicate identifiers")
    if any(name not in registry for name in names):
        raise ValueError("MCP_TOOLSETS contains an unsupported toolset identifier")
    # All selected settings are validated before any toolset enters its lifecycle.
    return [registry[name]()(configuration) for name in names]
