from tracy.adapters.notifications import macos


def test_macos_notification_sender_uses_notification_center(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments, **kwargs):
        calls.append(arguments)
        assert kwargs == {"check": True, "capture_output": True, "text": True}

    monkeypatch.setattr(macos.sys, "platform", "darwin")
    monkeypatch.setattr(macos.subprocess, "run", fake_run)

    macos.MacOSNotificationSender().send('Tracy "alert"', "Due today\nOpen Moodle")

    assert calls == [
        [
            "osascript",
            "-e",
            'display notification "Due today\\nOpen Moodle" with title "Tracy \\"alert\\""',
        ]
    ]
