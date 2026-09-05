"""Shared, header-only model reader registry.

Readers are registered by extension and are deliberately kept behind this
small interface.  The registry does not import optional model libraries at
module import time; the built-in readers are installed lazily when the first
read or capability query is made.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ReaderFunction = Callable[..., tuple[dict, dict, int]]


@dataclass(frozen=True)
class ReaderCapabilities:
    """Safety and coverage information exposed by one reader."""

    name: str
    extensions: tuple[str, ...]
    metadata_only: bool = True
    loads_tensor_payloads: bool = False
    safe_by_default: bool = True
    optional_dependencies: tuple[str, ...] = ()
    supports_sharding: bool = False


ReaderCapability = ReaderCapabilities


@dataclass(frozen=True)
class RegisteredReader:
    """A reader implementation and its public capabilities."""

    function: ReaderFunction
    capabilities: ReaderCapabilities


class ReaderRegistry:
    """Dispatch model paths without coupling callers to format libraries."""

    def __init__(self) -> None:
        self._readers: dict[str, RegisteredReader] = {}

    def register(
        self,
        extensions: tuple[str, ...] | list[str] | str,
        function: ReaderFunction,
        capabilities: ReaderCapabilities,
    ) -> None:
        """Register a reader for one or more lower-case suffixes."""
        if isinstance(extensions, str):
            extensions = (extensions,)
        for extension in extensions:
            normalized = str(extension).lower()
            if not normalized.startswith("."):
                normalized = "." + normalized
            self._readers[normalized] = RegisteredReader(function, capabilities)

    def reader_for_path(self, filepath: str | Path) -> RegisteredReader:
        path = str(filepath).lower()
        candidates = sorted(self._readers, key=len, reverse=True)
        for extension in candidates:
            if path.endswith(extension):
                return self._readers[extension]
        suffix = Path(filepath).suffix.lower()
        raise ValueError(f"Unsupported model format: {suffix or '(none)'}")

    def capabilities(self, filepath: str | Path | None = None) -> list[ReaderCapabilities] | ReaderCapabilities:
        """Return all capabilities, or the capability for one path."""
        if filepath is not None:
            return self.reader_for_path(filepath).capabilities
        unique: dict[str, ReaderCapabilities] = {}
        for reader in self._readers.values():
            unique[reader.capabilities.name] = reader.capabilities
        return list(unique.values())

    def extensions(self, *, include_unsafe: bool = True) -> tuple[str, ...]:
        """Return registered extensions, optionally excluding unsafe defaults."""
        values = set()
        for extension, reader in self._readers.items():
            if include_unsafe or reader.capabilities.safe_by_default:
                values.add(extension)
        return tuple(sorted(values))

    def read(
        self,
        filepath: str,
        *,
        options: dict[str, Any] | None = None,
        checkpoint_safety: str = "reject",
        _skip_shards: bool = False,
    ) -> tuple[dict, dict, int]:
        """Read a header and aggregate a discovered shard set when applicable."""
        reader = self.reader_for_path(filepath)
        options = dict(options or {})

        if not _skip_shards:
            from .shard_discovery import aggregate_shard_headers, discover_shard_set

            shard_set = discover_shard_set(filepath)
            if shard_set and len(shard_set.members) > 1:
                return aggregate_shard_headers(
                    filepath,
                    shard_set,
                    lambda member_path: self.read(
                        member_path,
                        options=options,
                        checkpoint_safety=checkpoint_safety,
                        _skip_shards=True,
                    ),
                )

        kwargs: dict[str, Any] = {"options": options}
        if reader.capabilities.name == "checkpoint":
            kwargs["checkpoint_safety"] = checkpoint_safety
        return reader.function(filepath, **kwargs)


_DEFAULT_REGISTRY: ReaderRegistry | None = None
_BUILTINS_INSTALLED = False


def _install_builtin_readers(registry: ReaderRegistry) -> None:
    global _BUILTINS_INSTALLED
    if _BUILTINS_INSTALLED:
        return

    # This import is intentionally delayed.  In particular, importing the
    # application or querying capabilities must not import torch, onnx, or
    # gguf.  The built-in readers themselves only use header parsers.
    from model_readers import read_gguf_header, read_safetensors_header

    from .checkpoint_reader import read_checkpoint_header
    from .onnx_reader import read_onnx_header

    registry.register(
        (".safetensors", ".safetensors.index.json"),
        read_safetensors_header,
        ReaderCapabilities(
            name="safetensors",
            extensions=(".safetensors", ".safetensors.index.json"),
            supports_sharding=True,
        ),
    )
    registry.register(
        ".gguf",
        read_gguf_header,
        ReaderCapabilities(
            name="gguf",
            extensions=(".gguf",),
            optional_dependencies=("gguf",),
            supports_sharding=True,
        ),
    )
    registry.register(
        ".onnx",
        read_onnx_header,
        ReaderCapabilities(name="onnx", extensions=(".onnx",)),
    )
    registry.register(
        (".ckpt", ".pt", ".pth"),
        read_checkpoint_header,
        ReaderCapabilities(
            name="checkpoint",
            extensions=(".ckpt", ".pt", ".pth"),
            safe_by_default=False,
        ),
    )
    _BUILTINS_INSTALLED = True


def get_reader_registry() -> ReaderRegistry:
    """Return the process-wide registry with built-ins installed lazily."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ReaderRegistry()
    _install_builtin_readers(_DEFAULT_REGISTRY)
    return _DEFAULT_REGISTRY


def reader_capabilities(
    filepath: str | Path | None = None,
) -> list[ReaderCapabilities] | ReaderCapabilities:
    """Convenience API for integrations and diagnostics."""
    return get_reader_registry().capabilities(filepath)


get_default_reader_registry = get_reader_registry


__all__ = [
    "ReaderCapabilities",
    "ReaderCapability",
    "ReaderRegistry",
    "RegisteredReader",
    "get_reader_registry",
    "get_default_reader_registry",
    "reader_capabilities",
]
