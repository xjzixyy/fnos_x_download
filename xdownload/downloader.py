from __future__ import annotations

import re
import http.client
import socket
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
    query = urllib.parse.parse_qs(parsed.query)
    image_format = query.get("format", [""])[0].lower()
    if parsed.netloc.endswith("twimg.com") and image_format:
        image_name = query.get("name", [""])[0]
        basename = f"{basename}_{image_name}.{image_format}" if image_name else f"{basename}.{image_format}"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(basename).stem).strip("_") or "video"
    suffix = Path(basename).suffix.lower()
    if suffix not in (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".gif"):
        suffix = ".mp4"
    clean_resolution = "orig" if resolution == "原图" else re.sub(r"[^0-9xX]+", "", resolution) or "unknown"
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
        last_error: BaseException | None = None
        for attempt in range(1, self.max_request_attempts + 1):
            try:
                self._download_response(
                    lambda: urllib.request.urlopen(request, timeout=120),
                    target,
                    stop_event,
                    timeout_seconds,
                    start_time,
                    now,
                )
                return target
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if _is_connection_reset(exc):
                    try:
                        self._download_response(
                            lambda: self._open_ipv4(request, timeout=120),
                            target,
                            stop_event,
                            timeout_seconds,
                            start_time,
                            now,
                        )
                        return target
                    except (urllib.error.URLError, OSError) as ipv4_exc:
                        last_error = ipv4_exc
                if attempt >= self.max_request_attempts:
                    raise DownloadNetworkError(f"下载视频文件失败：{_describe_network_error(last_error)}") from last_error
                time.sleep(self.retry_delay_seconds)
        return target

    def _download_response(
        self,
        open_response: Callable[[], object],
        target: Path,
        stop_event: object | None,
        timeout_seconds: float,
        start_time: float,
        now: Callable[[], float],
    ) -> None:
        with open_response() as response, target.open("wb") as output:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise DownloadCancelled("任务已停止")
                if now() - start_time >= timeout_seconds:
                    raise DownloadTimeout("下载超时，已自动停止")
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)

    def _open_ipv4(self, request: urllib.request.Request, timeout: float) -> http.client.HTTPResponse:
        parsed = urllib.parse.urlparse(request.full_url)
        if parsed.scheme != "https":
            return urllib.request.urlopen(request, timeout=timeout)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        connection = IPv4HTTPSConnection(parsed.hostname or "", parsed.port or 443, timeout=timeout)
        connection.request(request.get_method(), path, headers=dict(request.header_items()))
        return connection.getresponse()


def _describe_network_error(exc: BaseException) -> str:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ConnectionResetError):
        return "连接被远端重置，请稍后重试，或检查服务器到 twittervideodownloader.com / video.twimg.com 的网络连通性"
    if isinstance(reason, TimeoutError):
        return "网络请求超时，请稍后重试"
    return str(exc)


def _is_connection_reset(exc: BaseException) -> bool:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return isinstance(reason, ConnectionResetError)


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        if not self.host:
            raise OSError("HTTPS host is empty")
        infos = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
        last_error: OSError | None = None
        for _family, socktype, proto, _canonname, sockaddr in infos:
            sock = socket.socket(socket.AF_INET, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                sock.connect(sockaddr)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                last_error = exc
                sock.close()
        if last_error:
            raise last_error
        raise OSError(f"没有可用的 IPv4 地址：{self.host}")
