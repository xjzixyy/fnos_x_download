from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Iterable


HOME_URL = "https://twittervideodownloader.com/en/"
DOWNLOAD_URL = "https://twittervideodownloader.com/download"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass(frozen=True)
class VideoGroup:
    title: str
    items: list[dict[str, str]]

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "items": self.items}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._active_href = html.unescape(href)
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._active_href:
            self.links.append((self._active_href, " ".join(self._active_text).strip()))
            self._active_href = None
            self._active_text = []


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.action = "/download"
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag.lower() == "form" and attr_map.get("id") == "myForm":
            self.in_form = True
            self.action = attr_map.get("action") or self.action
            return
        if self.in_form and tag.lower() == "input":
            name = attr_map.get("name")
            if name:
                self.fields[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self.in_form:
            self.in_form = False


def resolution_score(resolution: str) -> int:
    match = re.search(r"(\d{2,5})\s*x\s*(\d{2,5})", resolution)
    if not match:
        return 0
    width, height = int(match.group(1)), int(match.group(2))
    return width * height


def choose_highest_quality(groups: list[VideoGroup] | list[dict[str, object]]) -> dict[str, str]:
    if not groups:
        raise ValueError("没有提取到可下载的视频链接")
    first_group = groups[0]
    items = first_group.items if isinstance(first_group, VideoGroup) else first_group["items"]
    if not items:
        raise ValueError("第一个视频分组没有可下载链接")
    return max(items, key=lambda item: resolution_score(item.get("resolution", "")))


def parse_download_groups(download_html: str) -> list[VideoGroup]:
    parser = LinkParser()
    parser.feed(download_html)

    grouped: dict[str, list[dict[str, str]]] = {}
    group_order: list[str] = []
    seen_urls: set[str] = set()

    for href, text in parser.links:
        if not _looks_like_video_link(href):
            continue
        url = urllib.parse.urljoin(DOWNLOAD_URL, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        resolution = _extract_resolution(url, text)
        group_key = _media_group_key(url)
        if group_key not in grouped:
            grouped[group_key] = []
            group_order.append(group_key)
        grouped[group_key].append({"resolution": resolution, "url": url})

    return [
        VideoGroup(
            title=f"视频 {index}",
            items=sorted(grouped[key], key=lambda item: resolution_score(item["resolution"])),
        )
        for index, key in enumerate(group_order, start=1)
    ]


def _looks_like_video_link(href: str) -> bool:
    lowered = href.lower()
    return ".mp4" in lowered or "video.twimg.com" in lowered


def _extract_resolution(url: str, text: str) -> str:
    for source in (urllib.parse.unquote(url), text):
        match = re.search(r"(\d{2,5}\s*x\s*\d{2,5})", source)
        if match:
            return match.group(1).replace(" ", "")
    return "未知分辨率"


def _media_group_key(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path)
    if "/vid/" in path:
        return path.split("/vid/", 1)[0]
    return path.rsplit("/", 1)[0]


class TwitterVideoDownloaderExtractor:
    def __init__(
        self,
        opener: urllib.request.OpenerDirector | None = None,
        max_request_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self.opener = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        self.max_request_attempts = max(1, int(max_request_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    def extract(self, tweet_url: str) -> list[dict[str, object]]:
        cleaned_url = tweet_url.strip()
        if not cleaned_url:
            raise ValueError("请输入 X/Twitter 链接")

        home_html = self._request_text(HOME_URL, error_context="请求解析站首页")
        form = FormParser()
        form.feed(home_html)

        fields = dict(form.fields)
        fields["tweet"] = cleaned_url
        post_body = urllib.parse.urlencode(fields).encode("utf-8")
        target_url = urllib.parse.urljoin(HOME_URL, form.action)
        download_html = self._request_text(
            target_url,
            data=post_body,
            extra_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": HOME_URL,
            },
            error_context="提交解析请求",
        )
        groups = parse_download_groups(download_html)
        if not groups:
            raise ValueError("没有从下载页面提取到视频链接")
        return [group.to_dict() for group in groups]

    def _request_text(
        self,
        url: str,
        data: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        error_context: str = "请求解析站",
    ) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        for attempt in range(1, self.max_request_attempts + 1):
            try:
                with self.opener.open(request, timeout=45) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except (urllib.error.URLError, OSError) as exc:
                if attempt >= self.max_request_attempts:
                    raise RuntimeError(f"{error_context}失败：{_describe_network_error(exc)}") from exc
                time.sleep(self.retry_delay_seconds)
        raise RuntimeError(f"{error_context}失败")


def _describe_network_error(exc: BaseException) -> str:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ConnectionResetError):
        return "连接被远端重置，请稍后重试，或检查服务器到 twittervideodownloader.com / video.twimg.com 的网络连通性"
    if isinstance(reason, TimeoutError):
        return "网络请求超时，请稍后重试"
    return str(exc)
