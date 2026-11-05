"""Protect environment isolation when patching the known Dash renderer defect."""

import os
from pathlib import Path
import stat

import pytest

from benchmarks.dash_4_5.patch_partial_patterns import replace_bundle, transform_renderer


def test_bundle_replacement_preserves_uv_cache_hardlink(tmp_path: Path) -> None:
    """Replacing a package file must leave its shared cache inode unchanged.

    uv can link several environments to one cached bundle, so writing through
    an installed path would corrupt the pristine comparison as well.

    Args:
        tmp_path: Isolated directory for a fake cache and linked environment file.

    Returns:
        None.
    """
    cache = tmp_path / "cached.js"
    installed = tmp_path / "installed.js"
    cache.write_bytes(b"pristine renderer")
    cache.chmod(0o644)
    os.link(cache, installed)

    replace_bundle(installed, b"fixed renderer")

    assert cache.read_bytes() == b"pristine renderer"
    assert installed.read_bytes() == b"fixed renderer"
    assert cache.stat().st_ino != installed.stat().st_ino
    assert stat.S_IMODE(installed.stat().st_mode) == 0o644


def test_unrecognized_renderer_is_rejected() -> None:
    """A familiar-looking guard must not authorize patching an unknown build.

    The reviewed file hash is required even when the replacement text happens
    to occur once, preventing accidental edits after another Dash upgrade.

    Returns:
        None.
    """
    content = b"var keyPaths = paths.objs[idKeyStr];\n      if (keyPaths) {"
    with pytest.raises(ValueError, match="Unrecognized renderer"):
        transform_renderer(content, "dash_renderer.dev.js")
