"""Turn a Studio 5000 project file (.ACD) into the .L5X file our parser reads.

Rockwell's Logix Designer SDK does the actual conversion, and that SDK only
works on a computer that has Studio 5000 installed. This module is the one
place in the project that talks to the SDK, so everything else stays free
of Rockwell dependencies.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path


class IngestError(ValueError):
    """Raised when an .ACD file cannot be converted to .L5X."""


_SDK_MISSING = (
    "Converting .ACD files needs a computer with Studio 5000 and the "
    "Logix Designer SDK Python package (logix_designer_sdk) installed. "
    "On other computers, export the project as .L5X from Studio 5000 "
    "and use that file instead."
)

_DOTNET_MISSING = (
    "The Logix Designer SDK is installed but could not start its .NET "
    "engine. Install the 64-bit .NET 8 runtime (on ARM versions of "
    "Windows, the 32-bit runtime is needed as well) and try again. "
    "Details: {error}"
)

# Big projects can take minutes to open; this only guards against hangs.
_DEFAULT_TIMEOUT = 600.0


def acd_to_l5x(
    acd_path: str | Path,
    l5x_path: str | Path | None = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> Path:
    """Convert one .ACD file to .L5X and return the path of the new file.

    The .L5X is written next to the .ACD with the same name unless
    l5x_path says otherwise. An existing file at the target is replaced.
    """
    source = Path(acd_path)
    if not source.is_file():
        raise IngestError(f"no such file: {source}")
    if source.suffix.lower() != ".acd":
        raise IngestError(f"expected an .ACD file: {source.name}")
    target = Path(l5x_path) if l5x_path is not None else source.with_suffix(".L5X")
    if target.suffix.lower() != ".l5x":
        raise IngestError(f"the output file must end in .L5X: {target.name}")

    sdk, sdk_error = _load_sdk()
    try:
        asyncio.run(asyncio.wait_for(_convert(sdk, source, target), timeout))
    except (TimeoutError, asyncio.TimeoutError):
        raise IngestError(
            f"Studio 5000 did not finish converting {source.name} "
            f"within {int(timeout)} seconds."
        ) from None
    except sdk_error as error:
        raise IngestError(
            f"Studio 5000 could not convert {source.name}: {error}"
        ) from error
    return target


def _load_sdk():
    """Import the Rockwell SDK, or explain plainly why conversion can't run here."""
    _prepare_dotnet_env()
    try:
        import logix_designer_sdk
        from logix_designer_sdk.exceptions import LogixSdkError
    except ImportError:
        raise IngestError(_SDK_MISSING) from None
    except RuntimeError as error:
        # pythonnet raises RuntimeError when no usable .NET runtime is found
        raise IngestError(_DOTNET_MISSING.format(error=error)) from error
    return logix_designer_sdk, LogixSdkError


def _prepare_dotnet_env(environ=None) -> None:
    """Point each part of the SDK at the right .NET runtime when needed.

    The SDK runs as two programs: this 64-bit Python process and a 32-bit
    helper it launches. On ARM versions of Windows the 64-bit runtime
    lives in an "x64" subfolder that is not searched automatically, and
    pointing only the general setting (DOTNET_ROOT) at it would break the
    32-bit helper — so each side gets its own setting. Values the user
    has already set are left alone.
    """
    env = os.environ if environ is None else environ
    dotnet_x64 = Path(env.get("ProgramFiles", r"C:\Program Files")) / "dotnet" / "x64"
    if "DOTNET_ROOT" not in env and (dotnet_x64 / "shared").is_dir():
        env["DOTNET_ROOT"] = str(dotnet_x64)
    dotnet_x86 = Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "dotnet"
    if (dotnet_x86 / "shared").is_dir():
        env.setdefault("DOTNET_ROOT_X86", str(dotnet_x86))
        env.setdefault("DOTNET_ROOT(x86)", str(dotnet_x86))


async def _convert(sdk, source: Path, target: Path) -> None:
    project = await sdk.LogixProject.open_logix_project(str(source))
    try:
        # force=True replaces an existing target file; detailed_l5x stays off
        # so the output matches a plain Studio 5000 export.
        await project.save_as(str(target), True, False)
    finally:
        project.close()
