from __future__ import annotations

import threading
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .downloader import DownloadCancelled, DownloadTimeout
from .extractor import choose_highest_quality


@dataclass
class DownloadTask:
    id: int
    url: str
    download_dir: Path
    status: str
    created_at: float
    updated_at: float
    path: str = ""
    resolution: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "download_dir": str(self.download_dir),
            "status": self.status,
            "path": self.path,
            "resolution": self.resolution,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DownloadTask":
        status = str(payload.get("status") or "queued")
        if status in ("running", "stopping"):
            status = "queued"
        now = time.time()
        return cls(
            id=int(payload["id"]),
            url=str(payload["url"]),
            download_dir=Path(str(payload["download_dir"])),
            status=status,
            created_at=float(payload.get("created_at") or now),
            updated_at=float(payload.get("updated_at") or now),
            path=str(payload.get("path") or ""),
            resolution=str(payload.get("resolution") or ""),
            error=str(payload.get("error") or ""),
        )


class DownloadQueue:
    def __init__(
        self,
        extractor: Any,
        downloader: Any,
        queue_file: Path | str = "queue.json",
        auto_start: bool = True,
        max_concurrency: int = 1,
        task_timeout_seconds: int = 1800,
    ) -> None:
        self.extractor = extractor
        self.downloader = downloader
        self.queue_file = Path(queue_file)
        self.auto_start = auto_start
        self.max_concurrency = max(1, int(max_concurrency))
        self.task_timeout_seconds = max(1, int(task_timeout_seconds))
        self._tasks: list[DownloadTask] = []
        self._next_id = 1
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._workers: list[threading.Thread] = []
        self._stop_events: dict[int, threading.Event] = {}
        self._load()
        self._ensure_workers()

    def enqueue(self, url: str, download_dir: Path | str) -> dict[str, Any]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("请先输入链接")
        clean_download_dir = str(download_dir).strip()
        if not clean_download_dir:
            raise ValueError("请先设置下载目录")

        with self._lock:
            now = time.time()
            task = DownloadTask(
                id=self._next_id,
                url=clean_url,
                download_dir=Path(clean_download_dir),
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self._next_id += 1
            self._tasks.append(task)
            self._save()
            snapshot = task.to_dict()
            self._condition.notify()

        self._ensure_worker()
        return snapshot

    def retry(self, task_id: int) -> dict[str, Any]:
        with self._lock:
            source = self._find_task(task_id)
            if source.status not in ("failed", "stopped"):
                raise ValueError("只有失败或已停止任务可以重新加入队列")
            url = source.url
            download_dir = source.download_dir
        return self.enqueue(url, download_dir)

    def recover_urls(self, urls: list[str], download_dir: Path | str) -> list[dict[str, Any]]:
        tasks = []
        for url in urls:
            clean_url = url.strip()
            if clean_url:
                tasks.append(self.enqueue(clean_url, download_dir))
        return tasks

    def stop(self, task_id: int) -> dict[str, Any]:
        with self._lock:
            task = self._find_task(task_id)
            if task.status == "queued":
                task.status = "stopped"
                task.error = "任务已停止"
            elif task.status == "running":
                task.status = "stopping"
                task.error = "正在停止"
                event = self._stop_events.get(task.id)
                if event:
                    event.set()
            elif task.status == "stopping":
                pass
            else:
                raise ValueError("只有排队中或下载中的任务可以停止")
            task.updated_at = time.time()
            self._save()
            return task.to_dict()

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [task.to_dict() for task in self._tasks]

    def process_next(self) -> bool:
        task = self._claim_next_task()
        if task is None:
            return False

        try:
            stop_event = threading.Event()
            with self._lock:
                self._stop_events[task.id] = stop_event
            groups = self.extractor.extract(task.url)
            item = choose_highest_quality(groups)
            path = self.downloader.download(
                item,
                task.download_dir,
                stop_event=stop_event,
                timeout_seconds=self.task_timeout_seconds,
            )
            with self._lock:
                task.status = "success"
                task.path = str(path)
                task.resolution = item.get("resolution", "")
                task.error = ""
                task.updated_at = time.time()
                self._stop_events.pop(task.id, None)
                self._save()
        except (DownloadCancelled, DownloadTimeout) as exc:
            with self._lock:
                task.status = "stopped"
                task.error = str(exc)
                task.updated_at = time.time()
                self._stop_events.pop(task.id, None)
                self._save()
        except Exception as exc:
            with self._lock:
                task.status = "failed"
                task.error = str(exc)
                task.updated_at = time.time()
                self._stop_events.pop(task.id, None)
                self._save()
        return True

    def _ensure_workers(self) -> None:
        if not self.auto_start:
            return
        with self._lock:
            while len([worker for worker in self._workers if worker.is_alive()]) < self.max_concurrency:
                worker = threading.Thread(target=self._worker_loop, daemon=True)
                self._workers.append(worker)
                worker.start()

    def _ensure_worker(self) -> None:
        self._ensure_workers()

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not any(task.status == "queued" for task in self._tasks):
                    self._condition.wait()
            self.process_next()

    def _claim_next_task(self) -> DownloadTask | None:
        with self._lock:
            for task in self._tasks:
                if task.status == "queued":
                    task.status = "running"
                    task.updated_at = time.time()
                    self._save()
                    return task
        return None

    def _find_task(self, task_id: int) -> DownloadTask:
        for task in self._tasks:
            if task.id == task_id:
                return task
        raise ValueError("任务不存在")

    def _load(self) -> None:
        if not self.queue_file.exists():
            return
        payload = json.loads(self.queue_file.read_text(encoding="utf-8"))
        self._tasks = [DownloadTask.from_dict(item) for item in payload.get("tasks", [])]
        if self._tasks:
            self._next_id = max(task.id for task in self._tasks) + 1

    def _save(self) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tasks": [task.to_dict() for task in self._tasks]}
        temp_file = self.queue_file.with_suffix(self.queue_file.suffix + ".tmp")
        temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_file.replace(self.queue_file)
