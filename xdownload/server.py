from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import AppConfig, load_config
from .downloader import VideoDownloader
from .extractor import TwitterVideoDownloaderExtractor, choose_highest_quality
from .queue import DownloadQueue


PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>x下载</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #172033; }
    main { width: min(1120px, calc(100vw - 32px)); margin: 40px auto; }
    h1 { font-size: 28px; margin: 0 0 18px; letter-spacing: 0; }
    .layout { display: grid; grid-template-columns: minmax(320px, 440px) 1fr; gap: 18px; align-items: start; }
    label { display: block; margin: 0 0 8px; color: #374151; font-size: 14px; font-weight: 600; }
    input[type="text"] { width: 100%; box-sizing: border-box; border: 1px solid #cfd6e4; border-radius: 8px; padding: 11px 12px; font-size: 15px; line-height: 1.4; background: #fff; }
    textarea { width: 100%; min-height: 170px; box-sizing: border-box; resize: vertical; border: 1px solid #cfd6e4; border-radius: 8px; padding: 14px; font-size: 16px; line-height: 1.5; background: #fff; }
    .field { margin-top: 14px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 18px; }
    button { border: 0; border-radius: 8px; padding: 11px 16px; font-size: 15px; cursor: pointer; color: #fff; background: #1f6feb; }
    button.secondary { background: #4c5566; }
    button.retry { background: #b45309; padding: 7px 10px; font-size: 13px; }
    button.stop { background: #b42318; padding: 7px 10px; font-size: 13px; }
    button:disabled { cursor: wait; opacity: .66; }
    .panel { background: #fff; border: 1px solid #dde3ee; border-radius: 8px; padding: 16px; min-height: 240px; }
    .hint, .empty { color: #536179; margin: 0; line-height: 1.5; }
    .queue { display: grid; gap: 10px; }
    .task { border: 1px solid #e5e9f2; border-radius: 8px; padding: 12px; background: #fff; display: grid; grid-template-columns: 92px 1fr; gap: 12px; }
    .thumb { width: 92px; height: 92px; object-fit: cover; border-radius: 6px; background: #eef2f7; border: 1px solid #e5e9f2; }
    .thumb.placeholder { display: flex; align-items: center; justify-content: center; color: #7b8798; font-size: 13px; }
    .task-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; margin-bottom: 8px; }
    .url { min-width: 0; overflow-wrap: anywhere; color: #172033; }
    .badge { flex: 0 0 auto; border-radius: 999px; padding: 3px 9px; font-size: 12px; color: #fff; background: #64748b; }
    .badge.queued { background: #64748b; }
    .badge.running { background: #2563eb; }
    .badge.success { background: #15803d; }
    .badge.failed { background: #b42318; }
    .badge.stopping { background: #b45309; }
    .badge.stopped { background: #4c5566; }
    .meta { margin: 0; color: #536179; overflow-wrap: anywhere; line-height: 1.45; }
    .error { color: #b42318; }
    .path { color: #116329; word-break: break-all; }
    @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>x下载</h1>
  <div class="layout">
    <section class="panel">
      <label for="tweetInput">媒体链接</label>
      <textarea id="tweetInput" placeholder="粘贴 X/Twitter 图片或视频链接，每次提交会自动加入下载队列"></textarea>
      <div class="actions">
        <button class="secondary" id="pasteBtn" type="button">粘贴</button>
        <button id="enqueueBtn" type="button">加入队列</button>
      </div>
      <div class="field">
        <label for="downloadDirInput">基础下载地址</label>
        <input id="downloadDirInput" type="text" autocomplete="off" placeholder="/vol1/1000/downloads/xdownload">
      </div>
      <p class="hint" id="downloadDirText"></p>
      <p class="hint" id="messageText"></p>
    </section>
    <section class="panel">
      <div id="queuePanel" class="queue">
        <p class="empty">下载队列为空。</p>
      </div>
    </section>
  </div>
</main>
<script>
const input = document.querySelector("#tweetInput");
const downloadDirInput = document.querySelector("#downloadDirInput");
const queuePanel = document.querySelector("#queuePanel");
const messageText = document.querySelector("#messageText");
const downloadDirText = document.querySelector("#downloadDirText");
const buttons = [...document.querySelectorAll("button")];
let downloadDir = "";

async function loadDefaultConfig() {
  try {
    const data = await fetch("/api/config").then((response) => response.json());
    downloadDir = localStorage.getItem("xdownload.downloadDir") || data.download_dir || "";
    downloadDirInput.value = downloadDir;
    const concurrency = data.max_concurrency ? `；并发：${data.max_concurrency}` : "";
    const timeout = data.task_timeout_seconds ? `；超时：${data.task_timeout_seconds} 秒` : "";
    updateDownloadDirText(concurrency, timeout);
  } catch (error) {
    downloadDir = localStorage.getItem("xdownload.downloadDir") || "";
    downloadDirInput.value = downloadDir;
    updateDownloadDirText("", "");
  }
}

function updateDownloadDirText(concurrency = "", timeout = "") {
  const value = downloadDirInput.value.trim();
  downloadDirText.textContent = value ? `保存目录：${value}/YYYYMMDD${concurrency}${timeout}` : "";
}

function setBusy(isBusy) {
  buttons.forEach((button) => button.disabled = isBusy);
}

function showStatus(message, className = "status") {
  messageText.className = className;
  messageText.textContent = message;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function enqueueLink() {
  const tweetUrl = input.value.trim();
  if (!tweetUrl) {
    input.focus();
    throw new Error("请先输入链接");
  }
  downloadDir = downloadDirInput.value.trim();
  if (!downloadDir) {
    downloadDirInput.focus();
    throw new Error("下载目录未设置");
  }
  localStorage.setItem("xdownload.downloadDir", downloadDir);
  updateDownloadDirText();
  await postJson("/api/enqueue", {url: tweetUrl, download_dir: downloadDir});
  input.value = "";
  showStatus("已加入下载队列。");
  await loadQueue();
}

async function loadQueue() {
  const data = await fetch("/api/queue").then((response) => response.json());
  renderQueue(data.tasks || []);
}

function statusText(status) {
  return {
    queued: "排队中",
    running: "下载中",
    success: "完成",
    failed: "失败",
    stopping: "停止中",
    stopped: "已停止"
  }[status] || status;
}

function mediaText(mediaType) {
  return {video: "视频", image: "图片"}[mediaType] || "媒体";
}

function renderQueue(tasks) {
  if (!tasks.length) {
    queuePanel.innerHTML = `<p class="empty">下载队列为空。</p>`;
    return;
  }
  queuePanel.innerHTML = tasks.slice().reverse().map((task) => {
    const mediaType = task.media_type || "";
    const thumbnail = task.thumbnail_url
      ? `<img class="thumb" src="${escapeHtml(task.thumbnail_url)}" alt="">`
      : `<div class="thumb placeholder">${escapeHtml(mediaText(mediaType))}</div>`;
    const waitingText = mediaType === "image" ? "等待自动下载原图" : "等待自动提取最高分辨率";
    const resolutionLabel = mediaType === "image" ? "质量" : "分辨率";
    const detail = task.status === "success"
      ? `<p class="meta path">已保存：${escapeHtml(task.path)}</p>`
      : task.status === "failed"
        ? `<p class="meta error">${escapeHtml(task.error || "下载失败")}</p><button class="retry" data-id="${task.id}" type="button">重新加入队列</button>`
        : task.status === "stopped"
          ? `<p class="meta error">${escapeHtml(task.error || "任务已停止")}</p><button class="retry" data-id="${task.id}" type="button">重新加入队列</button>`
          : `<p class="meta">${task.resolution ? `${resolutionLabel}：${escapeHtml(task.resolution)}` : waitingText}</p><button class="stop" data-id="${task.id}" type="button">停止</button>`;
    return `<article class="task">
      ${thumbnail}
      <div>
        <div class="task-head">
          <div class="url">${escapeHtml(task.url)}</div>
          <span class="badge ${escapeHtml(task.status)}">${escapeHtml(statusText(task.status))}</span>
        </div>
        <p class="meta">${escapeHtml(mediaText(mediaType))}</p>
        ${detail}
      </div>
    </article>`;
  }).join("");
}

document.querySelector("#pasteBtn").addEventListener("click", async () => {
  try {
    input.value = await navigator.clipboard.readText();
  } catch (error) {
    input.value = "";
  }
  input.focus();
});

document.querySelector("#enqueueBtn").addEventListener("click", async () => {
  setBusy(true);
  try {
    await enqueueLink();
  } catch (error) {
    showStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
});

downloadDirInput.addEventListener("change", () => {
  downloadDir = downloadDirInput.value.trim();
  if (downloadDir) {
    localStorage.setItem("xdownload.downloadDir", downloadDir);
  }
  updateDownloadDirText();
});

queuePanel.addEventListener("click", async (event) => {
  const target = event.target;
  if (!target.matches(".retry")) return;
  try {
    await postJson("/api/retry", {id: Number(target.dataset.id)});
    showStatus("已重新加入下载队列。");
    await loadQueue();
  } catch (error) {
    showStatus(error.message, "error");
  }
});

queuePanel.addEventListener("click", async (event) => {
  const target = event.target;
  if (!target.matches(".stop")) return;
  try {
    await postJson("/api/stop", {id: Number(target.dataset.id)});
    showStatus("已请求停止任务。");
    await loadQueue();
  } catch (error) {
    showStatus(error.message, "error");
  }
});

input.addEventListener("keydown", async (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    document.querySelector("#enqueueBtn").click();
  }
});

loadDefaultConfig().then(loadQueue);
setInterval(loadQueue, 1500);
</script>
</body>
</html>
"""


def create_handler(
    config: AppConfig,
    extractor: Any,
    downloader: Any,
    download_queue: Any | None = None,
) -> type[BaseHTTPRequestHandler]:
    queue = download_queue or DownloadQueue(extractor, downloader)

    class XDownloadHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send_html(PAGE_HTML)
                return
            if self.path == "/api/config":
                self._send_json(
                    {
                        "ok": True,
                        "download_dir": str(config.download_dir),
                        "port": config.port,
                        "queue_file": str(config.queue_file),
                        "max_concurrency": config.max_concurrency,
                        "task_timeout_seconds": config.task_timeout_seconds,
                    }
                )
                return
            if self.path == "/api/queue":
                self._send_json({"ok": True, "tasks": queue.list_tasks()})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                payload = self._read_json()
                if self.path == "/api/enqueue":
                    task = self._enqueue_task(payload)
                    self._send_json({"ok": True, "task": task})
                    return
                if self.path == "/api/retry":
                    task = self._retry_task(payload)
                    self._send_json({"ok": True, "task": task})
                    return
                if self.path == "/api/stop":
                    task = self._stop_task(payload)
                    self._send_json({"ok": True, "task": task})
                    return
                if self.path == "/api/extract":
                    groups = extractor.extract(str(payload.get("url", "")))
                    self._send_json({"ok": True, "groups": groups})
                    return
                if self.path == "/api/download":
                    path = self._download_item(payload)
                    self._send_json({"ok": True, "path": str(path)})
                    return
                if self.path == "/api/auto-download":
                    groups = extractor.extract(str(payload.get("url", "")))
                    item = choose_highest_quality(groups)
                    path = self._download_item({"item": item, "download_dir": payload.get("download_dir")})
                    self._send_json({"ok": True, "groups": groups, "path": str(path)})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

        @staticmethod
        def _download_item(payload: dict[str, Any]) -> Path:
            item = payload.get("item")
            if not isinstance(item, dict):
                raise ValueError("下载参数无效")
            download_dir = str(payload.get("download_dir") or "").strip()
            if not download_dir:
                raise ValueError("请先设置下载目录")
            return downloader.download(item, Path(download_dir))

        @staticmethod
        def _enqueue_task(payload: dict[str, Any]) -> dict[str, Any]:
            url = str(payload.get("url") or "").strip()
            download_dir = str(payload.get("download_dir") or "").strip()
            if not download_dir:
                raise ValueError("请先设置下载目录")
            return queue.enqueue(url, Path(download_dir))

        @staticmethod
        def _retry_task(payload: dict[str, Any]) -> dict[str, Any]:
            return queue.retry(int(payload.get("id") or 0))

        @staticmethod
        def _stop_task(payload: dict[str, Any]) -> dict[str, Any]:
            return queue.stop(int(payload.get("id") or 0))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _send_html(self, body: str) -> None:
            content = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return XDownloadHandler


def run_server(config_path: Path | str = "config.json") -> None:
    config = load_config(config_path)
    extractor = TwitterVideoDownloaderExtractor()
    downloader = VideoDownloader(config.download_dir)
    download_queue = DownloadQueue(
        extractor,
        downloader,
        queue_file=config.queue_file,
        max_concurrency=config.max_concurrency,
        task_timeout_seconds=config.task_timeout_seconds,
    )
    handler = create_handler(config, extractor, downloader, download_queue)
    server = ThreadingHTTPServer(("0.0.0.0", config.port), handler)
    print(f"x下载已启动：http://127.0.0.1:{config.port}")
    print(f"默认下载目录：{config.download_dir}")
    server.serve_forever()
