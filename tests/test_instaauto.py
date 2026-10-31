"""Offline tests: YouTube and Instagram are mocked. Run with `python -m unittest`."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from instaauto import __main__ as app
from instaauto import state as st
from instaauto.config import Config
from instaauto.instagram import Instagram
from instaauto.youtube import Video, parse_api, parse_feed

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <yt:videoId>new2</yt:videoId><title>Newer</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/new2"/>
  <published>2026-10-31T10:00:00+00:00</published>
  <media:group><media:description>desc 2</media:description></media:group>
 </entry>
 <entry>
  <yt:videoId>new1</yt:videoId><title>Older</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=new1"/>
  <published>2026-10-30T10:00:00+00:00</published>
  <media:group><media:description>desc 1</media:description></media:group>
 </entry>
</feed>"""


def api_item(vid, title, published):
    return {"snippet": {"title": title, "description": f"about {vid}", "publishedAt": published,
                        "resourceId": {"videoId": vid}}}


def video(vid, published, url=None):
    return Video(vid, f"Title {vid}", f"Desc {vid}", url or f"https://www.youtube.com/watch?v={vid}", published)


class ParsingTests(unittest.TestCase):
    def test_parse_feed_oldest_first(self):
        videos = parse_feed(FEED)
        self.assertEqual([v.id for v in videos], ["new1", "new2"])
        self.assertEqual(videos[1].description, "desc 2")
        self.assertIn("/shorts/", videos[1].url)

    def test_parse_api_skips_private_and_sorts(self):
        videos = parse_api({"items": [
            api_item("b", "B", "2026-10-31T00:00:00Z"),
            api_item("x", "Private video", "2026-10-30T12:00:00Z"),
            api_item("a", "A", "2026-10-30T00:00:00Z"),
        ]})
        self.assertEqual([v.id for v in videos], ["a", "b"])
        self.assertEqual(videos[0].description, "about a")

    def test_caption_template(self):
        entry = {"title": "My {cool} Short", "description": "Line", "url": "u"}
        self.assertEqual(app.build_caption("{title}\\n\\n{description} {missing}", entry), "My {cool} Short\n\nLine")
        self.assertEqual(len(app.build_caption("{description}", {"description": "x" * 5000})), 2200)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(
            channel_id="UCabc", yt_api_key="key", ig_token="token", yt_cookies=None,
            caption_template="{title}", state_file=str(Path(self.tmp.name) / "state.json"),
            graph_version="v23.0", dry_run=False, max_attempts=2,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def state(self):
        return json.loads(Path(self.cfg.state_file).read_text(encoding="utf-8"))

    def test_first_run_posts_nothing_then_only_new_shorts(self):
        with mock.patch.object(app, "fetch_videos", return_value=[video("old", "2026-01-01")]):
            app.check(self.cfg)
        self.assertEqual(self.state()["videos"]["old"]["status"], st.SKIPPED)

        uploads = [video("old", "2026-01-01"), video("short1", "2026-10-31"), video("long1", "2026-10-30")]
        with mock.patch.object(app, "fetch_videos", return_value=uploads), \
             mock.patch.object(app, "is_short", side_effect=lambda v: v.id.startswith("short")):
            app.check(self.cfg)
        videos = self.state()["videos"]
        self.assertEqual(videos["short1"]["status"], st.PENDING)
        self.assertEqual(videos["long1"]["status"], st.SKIPPED)
        self.assertEqual(app.pending_ids(self.state(), 2), ["short1"])

    def _seed_pending(self):
        st.save(self.cfg.state_file, {"videos": {
            "s1": {"status": st.PENDING, "title": "S1", "published": "2026-10-31", "attempts": 0},
        }})

    def test_run_marks_posted(self):
        self._seed_pending()
        with mock.patch.object(app, "get_video", return_value=Path("s1.mp4")), \
             mock.patch.object(app.Instagram, "publish_reel", return_value="IG123") as publish:
            self.assertEqual(app.run(self.cfg), 0)
        publish.assert_called_once_with(Path("s1.mp4"), "S1")
        entry = self.state()["videos"]["s1"]
        self.assertEqual((entry["status"], entry["ig_media_id"]), (st.POSTED, "IG123"))
        self.assertEqual(app.pending_ids(self.state(), 2), [])

    def test_run_retries_then_gives_up(self):
        self._seed_pending()
        with mock.patch.object(app, "get_video", side_effect=RuntimeError("bot check")):
            self.assertEqual(app.run(self.cfg), 1)
            self.assertEqual(self.state()["videos"]["s1"]["status"], st.FAILED)
            self.assertEqual(app.run(self.cfg), 1)
        entry = self.state()["videos"]["s1"]
        self.assertEqual((entry["status"], entry["attempts"]), (st.GAVE_UP, 2))
        self.assertEqual(app.run(self.cfg), 0)  # no more retries

    def test_dry_run_changes_nothing(self):
        self._seed_pending()
        with mock.patch.object(app, "get_video") as get:
            self.assertEqual(app.run(replace(self.cfg, dry_run=True)), 0)
        get.assert_not_called()
        self.assertEqual(self.state()["videos"]["s1"]["status"], st.PENDING)


class InstagramTests(unittest.TestCase):
    def test_publish_reel_flow(self):
        def resp(data, code=200):
            r = mock.Mock(status_code=code, text=json.dumps(data))
            r.json.return_value = data
            return r

        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"0" * 1000)
            gets = [resp({"user_id": "42"}), resp({"status_code": "IN_PROGRESS"}), resp({"status_code": "FINISHED"})]
            posts = [resp({"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v23.0/C1"}),
                     resp({"success": True}), resp({"id": "MEDIA9"})]
            with mock.patch("instaauto.instagram.requests.get", side_effect=gets), \
                 mock.patch("instaauto.instagram.requests.post", side_effect=posts) as post, \
                 mock.patch("instaauto.instagram.time.sleep"):
                media_id = Instagram("tok").publish_reel(clip, "hello")

        self.assertEqual(media_id, "MEDIA9")
        create, upload, publish = post.call_args_list
        self.assertTrue(create.args[0].endswith("/42/media"))
        self.assertEqual(create.kwargs["data"]["media_type"], "REELS")
        self.assertEqual(upload.args[0], "https://rupload.facebook.com/ig-api-upload/v23.0/C1")
        self.assertEqual(upload.kwargs["headers"]["file_size"], "1000")
        self.assertEqual(publish.kwargs["data"]["creation_id"], "C1")


if __name__ == "__main__":
    unittest.main()
