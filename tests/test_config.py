import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xdownload.config import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_PORT,
    DEFAULT_QUEUE_FILE,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    load_config,
)


class ConfigTest(unittest.TestCase):
    def test_load_config_uses_defaults_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"

            config = load_config(config_path)

            self.assertEqual(config.download_dir, Path(DEFAULT_DOWNLOAD_DIR))
            self.assertEqual(config.port, DEFAULT_PORT)
            self.assertEqual(config.queue_file, Path(DEFAULT_QUEUE_FILE))
            self.assertEqual(config.max_concurrency, DEFAULT_MAX_CONCURRENCY)
            self.assertEqual(config.task_timeout_seconds, DEFAULT_TASK_TIMEOUT_SECONDS)
            self.assertFalse(config_path.exists())

    def test_load_config_uses_environment_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(
                os.environ,
                {
                    "XDOWNLOAD_DOWNLOAD_DIR": str(root / "from-env"),
                    "XDOWNLOAD_PORT": "8766",
                    "XDOWNLOAD_QUEUE_FILE": str(root / "queue.json"),
                    "XDOWNLOAD_MAX_CONCURRENCY": "3",
                    "XDOWNLOAD_TASK_TIMEOUT_SECONDS": "60",
                },
            ):
                config = load_config()

            self.assertEqual(config.download_dir, root / "from-env")
            self.assertEqual(config.port, 8766)
            self.assertEqual(config.queue_file, root / "queue.json")
            self.assertEqual(config.max_concurrency, 3)
            self.assertEqual(config.task_timeout_seconds, 60)
