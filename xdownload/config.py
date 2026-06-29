from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DOWNLOAD_DIR = "/Users/fl/Downloads/x下载"
DEFAULT_PORT = 8765
DEFAULT_QUEUE_FILE = "queue.json"
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_TASK_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class AppConfig:
    download_dir: Path
    port: int
    queue_file: Path
    max_concurrency: int
    task_timeout_seconds: int


def load_config(config_path: Path | str = "config.json") -> AppConfig:
    download_dir_value = os.environ.get("XDOWNLOAD_DOWNLOAD_DIR")
    port_value = os.environ.get("XDOWNLOAD_PORT")
    queue_file_value = os.environ.get("XDOWNLOAD_QUEUE_FILE")
    max_concurrency_value = os.environ.get("XDOWNLOAD_MAX_CONCURRENCY")
    task_timeout_value = os.environ.get("XDOWNLOAD_TASK_TIMEOUT_SECONDS")

    download_dir = Path(download_dir_value or DEFAULT_DOWNLOAD_DIR).expanduser()
    port = int(port_value or DEFAULT_PORT)
    queue_file = Path(queue_file_value or DEFAULT_QUEUE_FILE).expanduser()
    max_concurrency = max(1, int(max_concurrency_value or DEFAULT_MAX_CONCURRENCY))
    task_timeout_seconds = max(1, int(task_timeout_value or DEFAULT_TASK_TIMEOUT_SECONDS))
    return AppConfig(
        download_dir=download_dir,
        port=port,
        queue_file=queue_file,
        max_concurrency=max_concurrency,
        task_timeout_seconds=task_timeout_seconds,
    )
