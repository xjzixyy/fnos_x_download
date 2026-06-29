import tempfile
import unittest
import urllib.error
from datetime import date
from threading import Event
from unittest.mock import patch
from pathlib import Path

from xdownload.downloader import (
    DownloadCancelled,
    DownloadNetworkError,
    DownloadTimeout,
    VideoDownloader,
    build_filename,
    dated_download_dir,
    save_response_body,
)


class FakeResponse:
    headers = {}

    def __init__(self, chunks=None):
        self.chunks = list(chunks or [b""])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size):
        if self.chunks:
            return self.chunks.pop(0)
        return b""


class DownloaderTest(unittest.TestCase):
    def test_build_filename_keeps_resolution_and_mp4_suffix(self):
        filename = build_filename("https://video.twimg.com/foo/bar.mp4?tag=10", "720x1280")

        self.assertTrue(filename.endswith(".mp4"))
        self.assertIn("720x1280", filename)

    def test_save_response_body_writes_chunks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "video.mp4"
            chunks = [b"abc", b"", b"def"]

            result = save_response_body(chunks, target)

            self.assertEqual(target.read_bytes(), b"abcdef")
            self.assertEqual(result, target)

    def test_dated_download_dir_appends_yyyymmdd(self):
        target = dated_download_dir(
            Path("/vol1/1000/downloads/xdownload"),
            today=lambda: date(2026, 6, 9),
        )

        self.assertEqual(target, Path("/vol1/1000/downloads/xdownload/20260609"))

    def test_download_uses_request_download_dir_and_date_subdirectory(self):
        def fake_urlopen(request, timeout):
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            downloader = VideoDownloader(root / "default", today=lambda: date(2026, 6, 9))
            with patch("urllib.request.urlopen", fake_urlopen):
                path = downloader.download(
                    {
                        "resolution": "720x800",
                        "url": "https://video.twimg.com/amplify_video/foo/vid/avc1/720x800/file.mp4",
                    },
                    download_dir=root / "from-page",
                )

        self.assertEqual(path.parent, root / "from-page" / "20260609")

    def test_download_uses_twitter_referer_for_twitter_cdn(self):
        captured_requests = []

        def fake_urlopen(request, timeout):
            captured_requests.append(request)
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = VideoDownloader(Path(temp_dir), today=lambda: date(2026, 6, 9))
            with patch("urllib.request.urlopen", fake_urlopen):
                downloader.download(
                    {
                        "resolution": "720x800",
                        "url": "https://video.twimg.com/amplify_video/foo/vid/avc1/720x800/file.mp4",
                    }
                )

        self.assertEqual(captured_requests[0].headers["Referer"], "https://twitter.com/")

    def test_download_can_be_cancelled(self):
        stop_event = Event()

        class CancellingResponse(FakeResponse):
            def read(self, size):
                stop_event.set()
                return b"abc"

        def fake_urlopen(request, timeout):
            return CancellingResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = VideoDownloader(Path(temp_dir), today=lambda: date(2026, 6, 9))
            with patch("urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(DownloadCancelled):
                    downloader.download(
                        {"resolution": "720x800", "url": "https://video.twimg.com/foo.mp4"},
                        stop_event=stop_event,
                    )

    def test_download_times_out(self):
        def fake_urlopen(request, timeout):
            return FakeResponse(chunks=[b"abc", b""])
        times = iter([10.0, 10.002])

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = VideoDownloader(Path(temp_dir), today=lambda: date(2026, 6, 9))
            with patch("urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(DownloadTimeout):
                    downloader.download(
                        {"resolution": "720x800", "url": "https://video.twimg.com/foo.mp4"},
                        timeout_seconds=0.001,
                        now=lambda: next(times),
                    )

    def test_download_reports_connection_reset_with_context(self):
        def fake_urlopen(request, timeout):
            raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = VideoDownloader(Path(temp_dir), today=lambda: date(2026, 6, 9), retry_delay_seconds=0)
            with patch("urllib.request.urlopen", fake_urlopen):
                with self.assertRaisesRegex(DownloadNetworkError, "下载视频文件失败：连接被远端重置"):
                    downloader.download(
                        {"resolution": "720x800", "url": "https://video.twimg.com/foo.mp4"},
                    )
