from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

from .extractor import USER_AGENT


def build_filename(url: str, resolution: str) -> str:
    parsed = urllib.parse.urlparse(url)
    basename = Path(urllib.parse.unquote(parsed.path)).name or "video.mp4"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(basename).stem).strip("_") or "video"
    suffix = Path(basename).suffix if Path(basename).suffix.lower() == ".mp4" else ".mp4"
    clean_resolution = re.sub(r"[^0-9xX]+", "", resolution) or "unknown"
    return f"{int(time.time())}_{clean_resolution}_{stem}{suffix}"


def save_response_body(chunks: list[bytes] | tuple[bytes, ...], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        for chunk in chunks:
            if chunk:
                output.write(chunk)
    return target


def dated_download_dir(download_dir: Path, today: Callable[[], date] = date.today) -> Path:
    return download_dir.expanduser() / today().strftime("%Y%m%d")


class DownloadCancelled(RuntimeError):
    pass


class DownloadTimeout(RuntimeError):
    pass


class DownloadNetworkError(RuntimeError):
    pass


class VideoDownloader:
    def __init__(
        self,
        download_dir: Path,
        today: Callable[[], date] = date.today,
        max_request_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self.download_dir = download_dir
        self.today = today
        self.max_request_attempts = max(1, int(max_request_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    def download(
        self,
        item: dict[str, str],
        download_dir: Path | str | None = None,
        stop_event: object | None = None,
        timeout_seconds: float = 1800,
        now: Callable[[], float] = time.monotonic,
    ) -> Path:
        url = item.get("url", "")
        if not url:
            raise ValueError("下载链接为空")
        filename = build_filename(url, item.get("resolution", "unknown"))
        base_dir = Path(download_dir) if download_dir else self.download_dir
        target = dated_download_dir(base_dir, self.today) / filename
        start_time = now()

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://twitter.com/",
            },
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, self.max_request_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
                    while True:
                        if stop_event is not None and stop_event.is_set():
                            raise DownloadCancelled("任务已停止")
                        if now() - start_time >= timeout_seconds:
                            raise DownloadTimeout("下载超时，已自动停止")
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        output.write(chunk)
                break
            except (urllib.error.URLError, OSError) as exc:
                if attempt >= self.max_request_attempts:
                    raise DownloadNetworkError(f"下载视频文件失败：{_describe_network_error(exc)}") from exc
                time.sleep(self.retry_delay_seconds)
        return target


def _describe_network_error(exc: BaseException) -> str:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ConnectionResetError):
        return "连接被远端重置，请稍后重试，或检查服务器到 twittervideodownloader.com / video.twimg.com 的网络连通性"
    if isinstance(reason, TimeoutError):
        return "网络请求超时，请稍后重试"
    return str(exc)
