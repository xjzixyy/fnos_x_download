import unittest
import urllib.error

from xdownload.extractor import (
    VideoGroup,
    TwitterVideoDownloaderExtractor,
    choose_highest_quality,
    parse_download_groups,
    resolution_score,
)


SAMPLE_DOWNLOAD_HTML = """
<html>
  <body>
    <div class="card">
      <h3>Download Video 1</h3>
      <a class="btn" href="https://video.twimg.com/ext_tw_video/one/vid/320x568/a.mp4">Download 320x568</a>
      <a class="btn" href="https://video.twimg.com/ext_tw_video/one/vid/720x1280/b.mp4?tag=12">Download 720x1280</a>
    </div>
    <div class="card">
      <h3>Download Video 2</h3>
      <a href="https://video.twimg.com/ext_tw_video/two/vid/480x852/c.mp4">Download 480x852</a>
      <a href="https://video.twimg.com/ext_tw_video/two/vid/1280x720/d.mp4">Download 1280x720</a>
    </div>
  </body>
</html>
"""


class ExtractorTest(unittest.TestCase):
    def test_parse_download_groups_returns_grouped_resolutions(self):
        groups = parse_download_groups(SAMPLE_DOWNLOAD_HTML)

        self.assertEqual(
            groups,
            [
                VideoGroup(
                    title="视频 1",
                    items=[
                        {
                            "resolution": "320x568",
                            "url": "https://video.twimg.com/ext_tw_video/one/vid/320x568/a.mp4",
                        },
                        {
                            "resolution": "720x1280",
                            "url": "https://video.twimg.com/ext_tw_video/one/vid/720x1280/b.mp4?tag=12",
                        },
                    ],
                ),
                VideoGroup(
                    title="视频 2",
                    items=[
                        {
                            "resolution": "480x852",
                            "url": "https://video.twimg.com/ext_tw_video/two/vid/480x852/c.mp4",
                        },
                        {
                            "resolution": "1280x720",
                            "url": "https://video.twimg.com/ext_tw_video/two/vid/1280x720/d.mp4",
                        },
                    ],
                ),
            ],
        )

    def test_parse_download_groups_falls_back_to_single_group_without_cards(self):
        html = """
        <a href="https://video.twimg.com/amplify_video/foo/vid/360x640/file.mp4">Download</a>
        <a href="https://video.twimg.com/amplify_video/foo/vid/1080x1920/file.mp4">Download</a>
        """

        groups = parse_download_groups(html)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].title, "视频 1")
        self.assertEqual([item["resolution"] for item in groups[0].items], ["360x640", "1080x1920"])

    def test_resolution_score_prefers_larger_pixel_area(self):
        self.assertGreater(resolution_score("720x1280"), resolution_score("480x852"))
        self.assertEqual(resolution_score("unknown"), 0)

    def test_choose_highest_quality_uses_first_group_only(self):
        groups = [
            VideoGroup(
                title="视频 1",
                items=[
                    {"resolution": "320x568", "url": "low"},
                    {"resolution": "720x1280", "url": "high"},
                ],
            ),
            VideoGroup(
                title="视频 2",
                items=[{"resolution": "1920x1080", "url": "ignored"}],
            ),
        ]

        self.assertEqual(choose_highest_quality(groups), {"resolution": "720x1280", "url": "high"})

    def test_extract_reports_connection_reset_during_home_request(self):
        class ResettingOpener:
            def open(self, request, timeout):
                raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))

        extractor = TwitterVideoDownloaderExtractor(ResettingOpener(), retry_delay_seconds=0)

        with self.assertRaisesRegex(RuntimeError, "请求解析站首页失败：连接被远端重置"):
            extractor.extract("https://x.com/a/status/1")
