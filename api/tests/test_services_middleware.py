import errno
import os
import queue
import types
import unittest
from unittest.mock import patch

from _support import TEST_ROOT

# main.py sets this before it imports librespot; the module under test
# imports librespot directly, so set it here too.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import requests

from onthespot import services_middleware


class _FakeFeeder:
    def __init__(self, error):
        self._error = error

    def load(self, *args, **kwargs):
        raise self._error


class _FakeSession:
    """Stands in for a librespot Session; only what download_spotify touches."""

    def __init__(self, error):
        self._feeder = _FakeFeeder(error)

    def content_feeder(self):
        return self._feeder


def _download(error):
    item = types.SimpleNamespace(download_format="mp3", item_status=None)
    token = _FakeSession(error)
    with patch("onthespot.services_middleware.reinit_spotify_session") as reinit:
        try:
            services_middleware.download_spotify(
                item, "0IVkP59yJ9GFF6B7IrvrxA", "track", token, str(TEST_ROOT / "track")
            )
        except Exception as exc:  # noqa: BLE001 - the test inspects the type
            return token, reinit, exc
    raise AssertionError("download_spotify did not raise")


class DownloadSpotifyDeadSessionTests(unittest.TestCase):
    def test_closed_socket_reinits_session(self):
        token, reinit, exc = _download(OSError(errno.EBADF, "Bad file descriptor"))
        reinit.assert_called_once_with(token)
        self.assertIsInstance(exc, RuntimeError)
        self.assertIn("connection lost", str(exc))

    def test_half_dead_socket_reinits_session(self):
        token, reinit, exc = _download(queue.Empty())
        reinit.assert_called_once_with(token)
        self.assertIsInstance(exc, RuntimeError)
        self.assertIn("connection lost", str(exc))

    def test_cdn_http_status_keeps_session(self):
        # librespot raises a bare IOError(status) when the CDN answers non-200.
        error = OSError("403")
        _token, reinit, exc = _download(error)
        reinit.assert_not_called()
        self.assertIs(exc, error)

    def test_cdn_transport_error_keeps_session(self):
        error = requests.exceptions.ConnectionError("cdn unreachable")
        _token, reinit, exc = _download(error)
        reinit.assert_not_called()
        self.assertIs(exc, error)


if __name__ == "__main__":
    unittest.main()
