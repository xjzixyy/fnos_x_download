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
    main { width: min(1180px, calc(100vw - 20px)); margin: 10px auto; }
    .layout { display: grid; grid-template-columns: minmax(300px, 400px) minmax(0, 1fr); gap: 14px; align-items: start; }
    .left-stack { display: grid; gap: 12px; }
    label { display: block; margin: 0 0 8px; color: #374151; font-size: 14px; font-weight: 600; }
    input[type="text"] { width: 100%; box-sizing: border-box; border: 1px solid #cfd6e4; border-radius: 8px; padding: 11px 12px; font-size: 15px; line-height: 1.4; background: #fff; }
    textarea { width: 100%; min-height: 150px; box-sizing: border-box; resize: vertical; border: 1px solid #cfd6e4; border-radius: 8px; padding: 14px; font-size: 16px; line-height: 1.5; background: #fff; }
    .actions { display: flex; margin: 12px 0 0; }
    button { border: 0; border-radius: 8px; padding: 11px 16px; font-size: 15px; cursor: pointer; color: #fff; background: #1f6feb; }
    #enqueueBtn { width: 100%; }
    button.retry { background: #b45309; padding: 4px 8px; font-size: 12px; border-radius: 6px; }
    button.stop { background: #b42318; padding: 4px 8px; font-size: 12px; border-radius: 6px; }
    button:disabled { cursor: wait; opacity: .66; }
    .panel { background: #fff; border: 1px solid #dde3ee; border-radius: 8px; padding: 14px; box-sizing: border-box; }
    .link-panel { min-height: 236px; }
    .path-panel { min-height: 0; }
    .queue-shell { max-height: calc(100vh - 20px); overflow-y: auto; }
    .queue-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; color: #536179; font-size: 13px; }
    .queue-title { color: #172033; font-weight: 700; font-size: 14px; }
    .queue-dir { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .hint, .empty { color: #536179; margin: 0; line-height: 1.5; }
    .queue { display: grid; gap: 6px; }
    .task { border: 1px solid #e5e9f2; border-radius: 8px; padding: 8px; background: #fff; display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 10px; align-items: center; }
    .thumb { width: 52px; height: 52px; object-fit: cover; border-radius: 6px; background: #eef2f7; border: 1px solid #e5e9f2; }
    .thumb.placeholder { display: flex; align-items: center; justify-content: center; color: #7b8798; font-size: 12px; }
    .task-main { min-width: 0; display: grid; gap: 4px; }
    .task-top { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .url { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #172033; font-size: 14px; }
    .task-actions { display: inline-flex; margin-left: 8px; vertical-align: middle; }
    .badge { flex: 0 0 auto; border-radius: 6px; padding: 2px 8px; font-size: 12px; line-height: 1.35; color: #fff; background: #64748b; }
    .badge.queued { background: #64748b; }
    .badge.running { background: #2563eb; }
    .badge.success { background: #15803d; }
    .badge.failed { background: #b42318; }
    .badge.stopping { background: #b45309; }
    .badge.stopped { background: #4c5566; }
    .meta { margin: 0; color: #536179; overflow-wrap: anywhere; line-height: 1.45; }
    .error { color: #b42318; }
    .path { color: #116329; word-break: break-all; }
    .detail { font-size: 13px; }
    @media (max-width: 760px) {
      .layout { grid-template-columns: 1fr; }
      .queue-shell { max-height: none; overflow-y: visible; }
    }
  </style>
</head>
<body>
<main>
  <div class="layout">
    <div class="left-stack">
      <section class="panel link-panel">
        <label for="tweetInput">媒体链接</label>
        <textarea id="tweetInput" placeholder="粘贴 X/Twitter 图片或视频链接；多个链接请每行一个"></textarea>
        <div class="actions">
          <button id="enqueueBtn" type="button">加入队列</button>
        </div>
      </section>
      <section class="panel path-panel">
        <label for="downloadDirInput">基础下载地址</label>
        <input id="downloadDirInput" type="text" autocomplete="off" placeholder="/vol1/1000/downloads/xdownload">
      </section>
    </div>
    <section class="panel queue-shell">
      <div class="queue-header">
        <span class="queue-title">下载队列</span>
        <span class="queue-dir" id="queueDirText"></span>
      </div>
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
const queueDirText = document.querySelector("#queueDirText");
const enqueueBtn = document.querySelector("#enqueueBtn");
let downloadDir = "";

async function loadDefaultConfig() {
  try {
    const data = await fetch("/api/config").then((response) => response.json());
    downloadDir = localStorage.getItem("xdownload.downloadDir") || data.download_dir || "";
    downloadDirInput.value = downloadDir;
    updateQueueDirText();
  } catch (error) {
    downloadDir = localStorage.getItem("xdownload.downloadDir") || "";
    downloadDirInput.value = downloadDir;
    updateQueueDirText();
  }
}

function setBusy(isBusy) {
  enqueueBtn.disabled = isBusy;
}

function updateQueueDirText() {
  const value = downloadDirInput.value.trim();
  queueDirText.textContent = value ? `保存目录：${value}/YYYYMMDD` : "";
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

function splitInputUrls(value) {
  return value.split(/\\r?\\n/).map((url) => url.trim()).filter(Boolean);
}

async function enqueueLink() {
  const tweetUrls = splitInputUrls(input.value);
  if (!tweetUrls.length) {
    input.focus();
    throw new Error("请先输入链接");
  }
  downloadDir = downloadDirInput.value.trim();
  if (!downloadDir) {
    downloadDirInput.focus();
    throw new Error("下载目录未设置");
  }
  localStorage.setItem("xdownload.downloadDir", downloadDir);
  updateQueueDirText();
  await postJson("/api/enqueue", {urls: tweetUrls, download_dir: downloadDir});
  input.value = "";
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
    const action = task.status === "failed" || task.status === "stopped"
      ? `<button class="retry" data-id="${task.id}" type="button">重试</button>`
      : task.status === "success"
        ? ""
        : `<button class="stop" data-id="${task.id}" type="button">停止</button>`;
    const detail = task.status === "success"
      ? `<p class="meta path detail">已保存：${escapeHtml(task.path)}</p>`
      : task.status === "failed"
        ? `<p class="meta error detail">${escapeHtml(task.error || "下载失败")}${action ? `<span class="task-actions">${action}</span>` : ""}</p>`
        : task.status === "stopped"
          ? `<p class="meta error detail">${escapeHtml(task.error || "任务已停止")}${action ? `<span class="task-actions">${action}</span>` : ""}</p>`
          : `<p class="meta detail">${task.resolution ? `${resolutionLabel}：${escapeHtml(task.resolution)}` : waitingText}${action ? `<span class="task-actions">${action}</span>` : ""}</p>`;
    return `<article class="task">
      ${thumbnail}
      <div class="task-main">
        <div class="task-top">
          <span class="badge ${escapeHtml(task.status)}">${escapeHtml(statusText(task.status))}</span>
          <span class="meta">${escapeHtml(mediaText(mediaType))}</span>
        </div>
        <div class="url" title="${escapeHtml(task.url)}">${escapeHtml(task.url)}</div>
        ${detail}
      </div>
    </article>`;
  }).join("");
}

document.querySelector("#enqueueBtn").addEventListener("click", async () => {
  setBusy(true);
  try {
    await enqueueLink();
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
  }
});

downloadDirInput.addEventListener("change", () => {
  downloadDir = downloadDirInput.value.trim();
  if (downloadDir) {
    localStorage.setItem("xdownload.downloadDir", downloadDir);
  }
  updateQueueDirText();
});

queuePanel.addEventListener("click", async (event) => {
  const target = event.target;
  if (!target.matches(".retry")) return;
  try {
    await postJson("/api/retry", {id: Number(target.dataset.id)});
    await loadQueue();
  } catch (error) {
    alert(error.message);
  }
});

queuePanel.addEventListener("click", async (event) => {
  const target = event.target;
  if (!target.matches(".stop")) return;
  try {
    await postJson("/api/stop", {id: Number(target.dataset.id)});
    await loadQueue();
  } catch (error) {
    alert(error.message);
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
                    result = self._enqueue_task(payload)
                    if "tasks" in result:
                        self._send_json({"ok": True, **result})
                    else:
                        self._send_json({"ok": True, "task": result, "count": 1})
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
            download_dir = str(payload.get("download_dir") or "").strip()
            if not download_dir:
                raise ValueError("请先设置下载目录")
            urls = payload.get("urls")
            if isinstance(urls, list):
                cleaned_urls = [str(url).strip() for url in urls if str(url).strip()]
                if not cleaned_urls:
                    raise ValueError("请先输入链接")
                tasks = [queue.enqueue(url, Path(download_dir)) for url in cleaned_urls]
                return {"count": len(tasks), "tasks": tasks}
            url = str(payload.get("url") or "").strip()
            if not url:
                raise ValueError("请先输入链接")
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
