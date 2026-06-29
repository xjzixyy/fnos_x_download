from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def load_queue(queue_file: Path) -> dict:
    if queue_file.exists():
        return json.loads(queue_file.read_text(encoding="utf-8"))
    return {"tasks": []}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: recover_queue.py urls.txt", file=sys.stderr)
        return 2

    url_file = Path(sys.argv[1])
    queue_file = Path(os.environ.get("XDOWNLOAD_QUEUE_FILE", "/var/apps/xdownload/data/queue.json"))
    download_dir = os.environ.get("XDOWNLOAD_DOWNLOAD_DIR", "/var/apps/xdownload/data/downloads")
    urls = [line.strip() for line in url_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    payload = load_queue(queue_file)
    tasks = payload.setdefault("tasks", [])
    existing = {task.get("url") for task in tasks if task.get("status") in {"queued", "running", "stopping"}}
    next_id = max([int(task.get("id", 0)) for task in tasks] + [0]) + 1
    now = time.time()
    added = 0

    for url in urls:
        if url in existing:
            continue
        tasks.append(
            {
                "id": next_id,
                "url": url,
                "download_dir": download_dir,
                "status": "queued",
                "path": "",
                "resolution": "",
                "error": "",
                "created_at": now,
                "updated_at": now,
            }
        )
        next_id += 1
        added += 1

    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"added={added} queue_file={queue_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
