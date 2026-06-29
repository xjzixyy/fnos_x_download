import json
import unittest
from pathlib import Path

from xdownload.config import AppConfig
from xdownload.server import PAGE_HTML, create_handler


class FakeExtractor:
    def __init__(self):
        self.urls = []

    def extract(self, tweet_url):
        self.urls.append(tweet_url)
        return [
            {
                "title": "视频 1",
                "items": [{"resolution": "720x1280", "url": "https://example.com/a.mp4"}],
            }
        ]


class FakeDownloader:
    def __init__(self):
        self.calls = []

    def download(self, item, download_dir=None):
        self.calls.append((item, download_dir))
        return Path("/tmp/video.mp4")


class FakeQueue:
    def __init__(self):
        self.enqueued = []
        self.retried = []

    def enqueue(self, url, download_dir):
        self.enqueued.append((url, download_dir))
        return {"id": 1, "url": url, "download_dir": str(download_dir), "status": "queued"}

    def list_tasks(self):
        return [{"id": 1, "url": "https://x.com/a", "status": "queued"}]

    def retry(self, task_id):
        self.retried.append(task_id)
        return {"id": 2, "url": "https://x.com/a", "status": "queued"}

    def stop(self, task_id):
        return {"id": task_id, "url": "https://x.com/a", "status": "stopping"}


class ServerTest(unittest.TestCase):
    def test_page_has_download_dir_input(self):
        self.assertIn('id="downloadDirInput"', PAGE_HTML)
        self.assertIn("基础下载地址", PAGE_HTML)

    def test_page_renders_task_thumbnail(self):
        self.assertIn("thumbnail_url", PAGE_HTML)
        self.assertIn('class="thumb"', PAGE_HTML)
        self.assertIn("media_type", PAGE_HTML)

    def test_create_handler_returns_handler_class(self):
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
        )

        self.assertEqual(handler.__name__, "XDownloadHandler")

    def test_download_dir_from_payload_is_passed_to_downloader(self):
        downloader = FakeDownloader()
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            downloader,
        )
        payload = {
            "item": {"resolution": "720x1280", "url": "https://example.com/a.mp4"},
            "download_dir": "/vol1/1000/videos",
        }

        result = handler._download_item(payload)

        self.assertEqual(result, Path("/tmp/video.mp4"))
        self.assertEqual(downloader.calls[0][1], Path("/vol1/1000/videos"))

    def test_download_without_page_directory_is_rejected(self):
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
        )

        with self.assertRaisesRegex(ValueError, "请先设置下载目录"):
            handler._download_item(
                {"item": {"resolution": "720x1280", "url": "https://example.com/a.mp4"}}
            )

    def test_enqueue_payload_uses_queue(self):
        queue = FakeQueue()
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
            queue,
        )

        task = handler._enqueue_task(
            {"url": "https://x.com/a", "download_dir": "/vol1/1000/videos"}
        )

        self.assertEqual(task["status"], "queued")
        self.assertEqual(queue.enqueued[0], ("https://x.com/a", Path("/vol1/1000/videos")))

    def test_batch_enqueue_payload_uses_queue_for_each_url(self):
        queue = FakeQueue()
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
            queue,
        )

        result = handler._enqueue_task(
            {
                "urls": ["https://x.com/a", "", " https://x.com/b "],
                "download_dir": "/vol1/1000/videos",
            }
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(
            queue.enqueued,
            [
                ("https://x.com/a", Path("/vol1/1000/videos")),
                ("https://x.com/b", Path("/vol1/1000/videos")),
            ],
        )

    def test_page_splits_multiline_links_for_batch_enqueue(self):
        self.assertIn("splitInputUrls", PAGE_HTML)
        self.assertIn(r"split(/\r?\n/)", PAGE_HTML)
        self.assertNotIn("split(/\r?\n/)", PAGE_HTML)
        self.assertIn("urls: tweetUrls", PAGE_HTML)
        self.assertNotIn("已加入 ${data.count || tweetUrls.length} 条链接", PAGE_HTML)
        self.assertNotIn('id="pasteBtn"', PAGE_HTML)
        self.assertIn('class="task-actions"', PAGE_HTML)

    def test_page_uses_window_title_without_inner_brand(self):
        self.assertNotIn('class="brand-logo"', PAGE_HTML)
        self.assertNotIn('src="/assets/icon.png"', PAGE_HTML)
        self.assertNotIn("<h1>x下载</h1>", PAGE_HTML)
        self.assertIn("<title>x下载</title>", PAGE_HTML)

    def test_page_uses_compact_form_and_scrollable_queue(self):
        self.assertIn('class="left-stack"', PAGE_HTML)
        self.assertIn('class="panel link-panel"', PAGE_HTML)
        self.assertIn('class="panel path-panel"', PAGE_HTML)
        self.assertIn('id="enqueueBtn"', PAGE_HTML)
        self.assertIn("#enqueueBtn { width: 100%; }", PAGE_HTML)
        self.assertNotIn('id="downloadDirText"', PAGE_HTML)
        self.assertIn("保存目录：", PAGE_HTML)
        self.assertIn("queue-shell", PAGE_HTML)
        self.assertIn("queue-header", PAGE_HTML)

    def test_enqueue_without_download_dir_is_rejected(self):
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
            FakeQueue(),
        )

        with self.assertRaisesRegex(ValueError, "请先设置下载目录"):
            handler._enqueue_task({"url": "https://x.com/a"})

    def test_retry_payload_uses_queue(self):
        queue = FakeQueue()
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
            queue,
        )

        task = handler._retry_task({"id": 5})

        self.assertEqual(task["status"], "queued")
        self.assertEqual(queue.retried, [5])

    def test_stop_payload_uses_queue(self):
        queue = FakeQueue()
        handler = create_handler(
            AppConfig(download_dir=Path("/tmp/default"), port=8888, queue_file=Path("/tmp/queue.json"), max_concurrency=2, task_timeout_seconds=30),
            FakeExtractor(),
            FakeDownloader(),
            queue,
        )

        task = handler._stop_task({"id": 5})

        self.assertEqual(task["status"], "stopping")
