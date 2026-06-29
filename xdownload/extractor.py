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


class VideoCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, object]] = []
        self._current_card: dict[str, object] | None = None
        self._active_href: str | None = None
        self._active_text: list[str] = []
        self._div_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        lowered_tag = tag.lower()
        if lowered_tag == "div":
            class_value = attr_map.get("class", "")
            classes = set(class_value.split())
            marker = ""
            if "card" in classes:
                self._current_card = {"links": [], "thumbnail_url": ""}
                marker = "card"
            elif "card-body" in classes:
                marker = "card-body"
            elif "text-center" in classes:
                marker = "text-center"
            self._div_stack.append(marker)
            return
        if self._current_card is None:
            return
        if lowered_tag == "img" and "card-body" in self._div_stack and "text-center" in self._div_stack:
            src = attr_map.get("src")
            if src and not self._current_card.get("thumbnail_url"):
                self._current_card["thumbnail_url"] = html.unescape(src)
            return
        if lowered_tag == "a":
            href = attr_map.get("href")
            if href:
                self._active_href = html.unescape(href)
                self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "a" and self._current_card is not None and self._active_href:
            links = self._current_card["links"]
            assert isinstance(links, list)
            links.append((self._active_href, " ".join(self._active_text).strip()))
            self._active_href = None
            self._active_text = []
            return
        if lowered_tag == "div" and self._div_stack:
            marker = self._div_stack.pop()
            if marker == "card" and self._current_card is not None:
                self.cards.append(self._current_card)
                self._current_card = None


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
    card_parser = VideoCardParser()
    card_parser.feed(download_html)
    if card_parser.cards:
        return _parse_card_download_groups(card_parser.cards)

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
        grouped[group_key].append({"media_type": "video", "resolution": resolution, "url": url, "thumbnail_url": ""})

    return [
        VideoGroup(
            title=f"视频 {index}",
            items=sorted(grouped[key], key=lambda item: resolution_score(item["resolution"])),
        )
        for index, key in enumerate(group_order, start=1)
    ]


def _parse_card_download_groups(cards: list[dict[str, object]]) -> list[VideoGroup]:
    groups: list[VideoGroup] = []
    for index, card in enumerate(cards, start=1):
        links = card.get("links") or []
        thumbnail_url = str(card.get("thumbnail_url") or "")
        items = []
        for href, text in links:
            if not _looks_like_video_link(str(href)):
                continue
            url = urllib.parse.urljoin(DOWNLOAD_URL, str(href))
            items.append(
                {
                    "media_type": "video",
                    "resolution": _extract_resolution(url, str(text)),
                    "url": url,
                    "thumbnail_url": thumbnail_url,
                }
            )
        if items:
            groups.append(
                VideoGroup(
                    title=f"视频 {index}",
                    items=sorted(items, key=lambda item: resolution_score(item["resolution"])),
                )
            )
    return groups


def extract_image_items(tweet_html: str) -> list[dict[str, str]]:
    pattern = r"https://pbs\.twimg\.com/media/[A-Za-z0-9_?&=;:./%-]+"
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_url in re.findall(pattern, html.unescape(tweet_html)):
        image_url, thumbnail_url = _normalize_image_urls(raw_url)
        if image_url in seen:
            continue
        seen.add(image_url)
        items.append(
            {
                "media_type": "image",
                "resolution": "原图",
                "url": image_url,
                "thumbnail_url": thumbnail_url,
            }
        )
    return items


def _normalize_image_urls(raw_url: str) -> tuple[str, str]:
    url = raw_url.rstrip(".,)")
    url = url.split('"', 1)[0].split("'", 1)[0]
    parsed = urllib.parse.urlparse(url)
    media_id = parsed.path.rsplit("/", 1)[-1]
    query = urllib.parse.parse_qs(parsed.query)
    image_format = query.get("format", [""])[0]
    if ":" in media_id:
        media_id, suffix = media_id.rsplit(":", 1)
        if "." in media_id:
            media_id, ext = media_id.rsplit(".", 1)
            image_format = image_format or ext
        image_format = image_format or ("jpg" if suffix else "")
    elif "." in media_id:
        media_id, ext = media_id.rsplit(".", 1)
        image_format = image_format or ext
    image_format = image_format or "jpg"
    base = f"https://pbs.twimg.com/media/{media_id}"
    return (
        f"{base}?format={image_format}&name=orig",
        f"{base}?format={image_format}&name=small",
    )


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
        groups = self.extract_video_groups(tweet_url)
        return [group.to_dict() for group in groups]

    def extract_media(self, tweet_url: str) -> list[dict[str, str]]:
        try:
            groups = self.extract_video_groups(tweet_url)
            return [choose_highest_quality([group]) for group in groups]
        except ValueError as exc:
            video_error = exc
        tweet_html = self._request_text(tweet_url.strip(), error_context="请求推文页面")
        if _tweet_html_has_video_marker(tweet_html):
            raise video_error
        media_items: list[dict[str, str]] = []
        media_items.extend(extract_image_items(tweet_html))
        if not media_items:
            raise ValueError("没有从推文中提取到图片或视频")
        return media_items

    def extract_video_groups(self, tweet_url: str) -> list[VideoGroup]:
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
        return groups

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


def _tweet_html_has_video_marker(tweet_html: str) -> bool:
    lowered = html.unescape(tweet_html).lower()
    video_markers = (
        'property="og:type" content="video',
        "property='og:type' content='video",
        'name="twitter:card" content="player"',
        "name='twitter:card' content='player'",
        'property="og:video',
        "property='og:video",
        "video.twimg.com",
        "data-testid=\"videoPlayer\"".lower(),
        "<video",
    )
    return any(marker in lowered for marker in video_markers)
