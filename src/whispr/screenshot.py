"""On-demand screen capture for the dictation-copilot's optional vision context.

GNOME/Wayland blocks arbitrary apps from org.gnome.Shell.Screenshot, so we go
through the sanctioned **xdg-desktop-portal** Screenshot API over DBus (dbus-fast,
pure-python — no gi in the lean daemon venv). The portal normally pops a consent
dialog per shot; setup-user.sh pre-grants it in the portal permission store so
capture is silent (see that script / the SetPermission call below).

    gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore \
      --object-path /org/freedesktop/impl/portal/PermissionStore \
      --method org.freedesktop.impl.portal.PermissionStore.SetPermission \
      "screenshot" true "screenshot" "" "['yes']"

The portal writes a PNG to ~/Pictures and hands back its URI; we load it, downscale
to a model-friendly size, JPEG-encode, delete the file, and return the bytes for an
OpenAI `input_image` content part. This is an un-unit-tested hardware/desktop seam
(like recorder/injector); the Rewriter calls it behind an injected `capture` seam.

Reference: rocky-linux/src/rocky/screenshot.py (same portal pattern).
"""

from __future__ import annotations

import asyncio
import io
import secrets
from pathlib import Path
from urllib.parse import unquote, urlparse

_PORTAL = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"


class ScreenshotError(Exception):
    """Raised when the portal refuses or the capture fails; message is user-facing."""


async def _portal_screenshot_uri(timeout: float = 15.0) -> str:
    """Call the portal Screenshot method and await its Response signal → file URI."""
    from dbus_fast import Variant
    from dbus_fast.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        intro = await bus.introspect(_PORTAL, _PORTAL_PATH)
        obj = bus.get_proxy_object(_PORTAL, _PORTAL_PATH, intro)
        screenshot = obj.get_interface("org.freedesktop.portal.Screenshot")

        # The reply arrives as a Response signal on a request path derived from our
        # unique bus name + our handle token (xdg portal request convention).
        token = "whispr" + secrets.token_hex(4)
        sender = bus.unique_name[1:].replace(".", "_")
        req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

        fut: asyncio.Future = asyncio.get_running_loop().create_future()

        def handler(msg) -> None:
            if msg.path == req_path and msg.member == "Response" and not fut.done():
                fut.set_result(msg.body)

        bus.add_message_handler(handler)
        await screenshot.call_screenshot(
            "", {"handle_token": Variant("s", token), "interactive": Variant("b", False)}
        )
        code, results = await asyncio.wait_for(fut, timeout=timeout)
        if code != 0:
            raise ScreenshotError(
                "the desktop portal denied the screenshot (permission not granted?)"
            )
        return results["uri"].value
    finally:
        bus.disconnect()


def _load_and_encode(png_path: Path, max_edge: int, quality: int) -> bytes:
    """Downscale the portal's PNG to `max_edge` (longest side) and JPEG-encode."""
    from PIL import Image

    with Image.open(png_path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge))  # no-op if already smaller
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


async def _capture_jpeg(max_edge: int, quality: int) -> bytes:
    uri = await _portal_screenshot_uri()
    path = Path(unquote(urlparse(uri).path))
    if not path.exists():
        raise ScreenshotError(f"portal reported {path}, but no file is there")
    try:
        return await asyncio.to_thread(_load_and_encode, path, max_edge, quality)
    finally:
        path.unlink(missing_ok=True)  # don't litter ~/Pictures with our shots


def capture_jpeg(max_edge: int = 2048, quality: int = 85) -> bytes:
    """Take a full-screen screenshot and return model-ready JPEG bytes. Synchronous.

    Runs the async portal exchange on a private event loop (the Daemon's rewrite
    runs on a worker thread with no loop of its own).
    """
    return asyncio.run(_capture_jpeg(max_edge, quality))


def make_screenshot_capturer(config):
    """Bind capture params from config into a zero-arg `() -> bytes` seam."""
    max_edge = getattr(config, "screenshot_max_edge", 2048)
    quality = getattr(config, "screenshot_quality", 85)
    return lambda: capture_jpeg(max_edge=max_edge, quality=quality)
