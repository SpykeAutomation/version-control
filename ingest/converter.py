"""Turn a Studio 5000 project file (.ACD) into the .L5X file our parser reads.

Rockwell's Logix Designer SDK does the actual conversion, and that SDK only
works on a computer that has Studio 5000 installed. This module is the one
place in the project that talks to the SDK, so everything else stays free
of Rockwell dependencies.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


class IngestError(ValueError):
    """Raised when an .ACD file cannot be converted to .L5X."""


_SDK_MISSING = (
    "Converting .ACD files needs a computer with Studio 5000 and the "
    "Logix Designer SDK Python package (logix_designer_sdk) installed. "
    "On other computers, export the project as .L5X from Studio 5000 "
    "and use that file instead."
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
    try:
        import logix_designer_sdk
        from logix_designer_sdk.exceptions import LogixSdkError
    except ImportError:
        raise IngestError(_SDK_MISSING) from None
    return logix_designer_sdk, LogixSdkError


async def _convert(sdk, source: Path, target: Path) -> None:
    project = await sdk.LogixProject.open_logix_project(str(source))
    try:
        # force=True replaces an existing target file; detailed_l5x stays off
        # so the output matches a plain Studio 5000 export.
        await project.save_as(str(target), True, False)
    finally:
        project.close()
