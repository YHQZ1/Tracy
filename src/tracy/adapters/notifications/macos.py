"""Native macOS notification adapter."""

from __future__ import annotations

import subprocess
import sys


class NotificationDeliveryError(RuntimeError):
    """Raised when the operating system cannot display a notification."""


def _escape_applescript_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MacOSNotificationSender:
    """Deliver a notification through macOS Notification Center."""

    def send(self, title: str, body: str) -> None:
        if sys.platform != "darwin":
            raise NotificationDeliveryError("Native notifications are only supported on macOS.")
        script = (
            f'display notification "{_escape_applescript_text(body)}" '
            f'with title "{_escape_applescript_text(title)}"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise NotificationDeliveryError(
                "macOS Notification Center rejected the notification."
            ) from error
