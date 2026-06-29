import tempfile
import time
import unittest
from threading import Event
from pathlib import Path

from xdownload.downloader import DownloadCancelled
from xdownload.queue import DownloadQueue


class FakeExtractor:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = set(failures or [])

    def extract(self, url):
        self.calls.append(url)
        if url in self.failures:
            raise RuntimeError("extract failed")
        return [
            {
                "title": "视频 1",
                "items": [
                    {"resolution": "320x240", "url": "https://example.com/low.mp4"},
                    {"resolution": "1280x720", "url": "https://example.com/high.mp4"},
                ],
            }
        ]


class FakeDownloader:
    def __init__(self):
        self.calls = []

    def download(self, item, download_dir, stop_event=None, timeout_seconds=1800):
        self.calls.append((item, download_dir))
        return Path(download_dir) / "20260610" / "video.mp4"


class BlockingDownloader:
    def __init__(self):
        self.started = 0
        self.release = Event()

    def download(self, item, download_dir, stop_event=None, timeout_seconds=1800):
        self.started += 1
        while not self.release.is_set():
            if stop_event is not None and stop_event.is_set():
                raise DownloadCancelled("任务已停止")
            time.sleep(0.001)
        return Path(download_dir) / "20260610" / f"{self.started}.mp4"


class DownloadQueueTest(unittest.TestCase):
    def test_enqueue_adds_queued_task_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(
                FakeExtractor(),
                FakeDownloader(),
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=False,
            )

            task = queue.enqueue("https://x.com/a", Path("/downloads"))

        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["url"], "https://x.com/a")
        self.assertEqual(task["download_dir"], "/downloads")

    def test_process_next_downloads_highest_resolution(self):
        downloader = FakeDownloader()
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(
                FakeExtractor(),
                downloader,
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=False,
            )
            queue.enqueue("https://x.com/a", Path("/downloads"))

            queue.process_next()

            tasks = queue.list_tasks()
        self.assertEqual(tasks[0]["status"], "success")
        self.assertEqual(tasks[0]["resolution"], "1280x720")
        self.assertEqual(tasks[0]["path"], "/downloads/20260610/video.mp4")
        self.assertEqual(downloader.calls[0][0]["url"], "https://example.com/high.mp4")
        self.assertEqual(downloader.calls[0][1], Path("/downloads"))

    def test_process_next_marks_failed_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(
                FakeExtractor(failures={"https://x.com/bad"}),
                FakeDownloader(),
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=False,
            )
            queue.enqueue("https://x.com/bad", Path("/downloads"))

            queue.process_next()

            tasks = queue.list_tasks()
        self.assertEqual(tasks[0]["status"], "failed")
        self.assertEqual(tasks[0]["error"], "extract failed")

    def test_retry_failed_task_appends_new_queued_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(
                FakeExtractor(failures={"https://x.com/bad"}),
                FakeDownloader(),
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=False,
            )
            failed = queue.enqueue("https://x.com/bad", Path("/downloads"))
            queue.process_next()

            retry = queue.retry(failed["id"])

            tasks = queue.list_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["status"], "failed")
        self.assertEqual(retry["status"], "queued")
        self.assertEqual(retry["url"], "https://x.com/bad")
        self.assertEqual(retry["download_dir"], "/downloads")

    def test_queue_persists_tasks_to_file_and_restores(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_file = Path(temp_dir) / "queue.json"
            queue = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=queue_file, auto_start=False)
            queue.enqueue("https://x.com/a", Path("/downloads"))

            restored = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=queue_file, auto_start=False)

            self.assertEqual(restored.list_tasks()[0]["url"], "https://x.com/a")
            self.assertEqual(restored.list_tasks()[0]["status"], "queued")

    def test_running_tasks_are_restored_as_queued_after_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_file = Path(temp_dir) / "queue.json"
            queue = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=queue_file, auto_start=False)
            queue.enqueue("https://x.com/a", Path("/downloads"))
            task = queue._claim_next_task()
            queue._save()
            self.assertEqual(task.status, "running")

            restored = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=queue_file, auto_start=False)

            self.assertEqual(restored.list_tasks()[0]["status"], "queued")

    def test_stop_marks_running_task_stopped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = BlockingDownloader()
            queue = DownloadQueue(
                FakeExtractor(),
                downloader,
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=True,
                max_concurrency=1,
            )
            task = queue.enqueue("https://x.com/a", Path("/downloads"))
            deadline = time.time() + 1
            while queue.list_tasks()[0]["status"] != "running" and time.time() < deadline:
                time.sleep(0.001)

            stopped = queue.stop(task["id"])
            deadline = time.time() + 1
            while queue.list_tasks()[0]["status"] in ("running", "stopping") and time.time() < deadline:
                time.sleep(0.001)
            downloader.release.set()

            self.assertEqual(stopped["status"], "stopping")
            self.assertEqual(queue.list_tasks()[0]["status"], "stopped")

    def test_auto_start_uses_configured_concurrency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = BlockingDownloader()
            queue = DownloadQueue(
                FakeExtractor(),
                downloader,
                queue_file=Path(temp_dir) / "queue.json",
                auto_start=True,
                max_concurrency=2,
            )
            queue.enqueue("https://x.com/a", Path("/downloads"))
            queue.enqueue("https://x.com/b", Path("/downloads"))
            deadline = time.time() + 1
            while downloader.started < 2 and time.time() < deadline:
                time.sleep(0.001)
            downloader.release.set()

            self.assertEqual(downloader.started, 2)

    def test_recover_urls_appends_queued_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=Path(temp_dir) / "queue.json", auto_start=False)

            tasks = queue.recover_urls(["https://x.com/a", "", "https://x.com/b"], Path("/downloads"))

            self.assertEqual([task["url"] for task in tasks], ["https://x.com/a", "https://x.com/b"])
            self.assertEqual([task["status"] for task in tasks], ["queued", "queued"])

    def test_retry_stopped_task_appends_new_queued_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = DownloadQueue(FakeExtractor(), FakeDownloader(), queue_file=Path(temp_dir) / "queue.json", auto_start=False)
            task = queue.enqueue("https://x.com/a", Path("/downloads"))
            queue.stop(task["id"])

            retry = queue.retry(task["id"])

            self.assertEqual(retry["status"], "queued")
            self.assertEqual(retry["url"], "https://x.com/a")


if __name__ == "__main__":
    unittest.main()
