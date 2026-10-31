"""Offline tests: Google Drive and Instagram are mocked. Run with `python -m unittest`."""

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from instaauto import __main__ as app
from instaauto import state as st
from instaauto.config import Config
from instaauto.drive import folder_id_from
from instaauto.instagram import Instagram

OLD = "2026-10-30T10:00:00.000Z"


def drive_file(fid, name, created=OLD, mime="video/mp4"):
    return {"id": fid, "name": name, "mimeType": mime, "createdTime": created}


class FakeDrive:
    def __init__(self, videos, captions=None, texts=None):
        self.videos, self.captions, self.texts = videos, captions or {}, texts or {}
        self.moved = []

    def list_folder(self):
        return self.videos, self.captions

    def read_text(self, file_id):
        return self.texts[file_id]

    def download(self, file_id, dest):
        return dest

    def move(self, file_id, subfolder):
        self.moved.append((file_id, subfolder))


class HelperTests(unittest.TestCase):
    def test_folder_id_from_link_or_id(self):
        self.assertEqual(folder_id_from("https://drive.google.com/drive/folders/1AbC_xyz?usp=sharing"), "1AbC_xyz")
        self.assertEqual(folder_id_from(" 1AbC_xyz "), "1AbC_xyz")

    def test_caption_template(self):
        self.assertEqual(app.build_caption("{caption}\\n\\n#shorts {missing}", "Hi {there}", "a.mp4"), "Hi {there}\n\n#shorts")
        self.assertEqual(len(app.build_caption("{caption}", "x" * 5000, "a.mp4")), 2200)

    def test_is_too_new(self):
        just_now = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertTrue(app.is_too_new(just_now, 5))
        self.assertFalse(app.is_too_new(OLD, 5))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(
            drive_folder_id="F", drive_credentials="{}", ig_token="token",
            caption_template="{caption}", state_file=str(Path(self.tmp.name) / "state.json"),
            graph_version="v23.0", dry_run=False, max_attempts=2, max_posts_per_run=1, min_age_minutes=5,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def state(self):
        return json.loads(Path(self.cfg.state_file).read_text(encoding="utf-8"))

    def patch_drive(self, drive):
        return mock.patch.object(app, "Drive", return_value=drive)

    def test_check_finds_new_videos_and_waits_for_fresh_uploads(self):
        fresh = datetime.now(timezone.utc).isoformat()
        drive = FakeDrive([drive_file("v1", "trip.mp4"), drive_file("v2", "new.mp4", created=fresh)])
        with self.patch_drive(drive):
            app.check(self.cfg)
        self.assertEqual(list(self.state()["videos"]), ["v1"])
        self.assertEqual(self.state()["videos"]["v1"]["status"], st.PENDING)

    def _seed(self, *names):
        st.save(self.cfg.state_file, {"videos": {
            f"v{i}": {"status": st.PENDING, "name": n, "created": f"2026-10-3{i}", "attempts": 0}
            for i, n in enumerate(names)
        }})

    def test_run_posts_with_txt_caption_and_moves_files(self):
        self._seed("trip.mp4")
        drive = FakeDrive([], captions={"trip": "c1"}, texts={"c1": "Goa trip 🌴"})
        with self.patch_drive(drive), \
             mock.patch.object(app, "ensure_instagram_compatible", side_effect=lambda p: p), \
             mock.patch.object(app.Instagram, "publish_reel", return_value="IG1") as publish:
            self.assertEqual(app.run(self.cfg), 0)
        publish.assert_called_once_with(Path("tmp/v0.mp4"), "Goa trip 🌴")
        self.assertEqual(self.state()["videos"]["v0"]["status"], st.POSTED)
        self.assertEqual(drive.moved, [("v0", "Posted"), ("c1", "Posted")])

    def test_run_uses_file_name_without_txt_and_one_per_run(self):
        self._seed("First clip.mp4", "Second clip.mov")
        drive = FakeDrive([])
        with self.patch_drive(drive), \
             mock.patch.object(app, "ensure_instagram_compatible", side_effect=lambda p: p), \
             mock.patch.object(app.Instagram, "publish_reel", return_value="IG1") as publish:
            app.run(self.cfg)
        publish.assert_called_once_with(Path("tmp/v0.mp4"), "First clip")
        self.assertEqual(self.state()["videos"]["v1"]["status"], st.PENDING)

    def test_run_retries_then_moves_to_failed(self):
        self._seed("bad.mp4")
        drive = FakeDrive([])
        with self.patch_drive(drive), \
             mock.patch.object(app, "ensure_instagram_compatible", side_effect=RuntimeError("broken file")):
            self.assertEqual(app.run(self.cfg), 1)
            self.assertEqual(drive.moved, [])
            self.assertEqual(app.run(self.cfg), 1)
        entry = self.state()["videos"]["v0"]
        self.assertEqual((entry["status"], entry["attempts"]), (st.GAVE_UP, 2))
        self.assertEqual(drive.moved, [("v0", "Failed")])
        self.assertEqual(app.run(self.cfg), 0)  # no more retries

    def test_move_failure_does_not_break_posting(self):
        self._seed("a.mp4")
        drive = FakeDrive([])
        drive.move = mock.Mock(side_effect=RuntimeError("no permission"))
        with self.patch_drive(drive), \
             mock.patch.object(app, "ensure_instagram_compatible", side_effect=lambda p: p), \
             mock.patch.object(app.Instagram, "publish_reel", return_value="IG1"):
            self.assertEqual(app.run(self.cfg), 0)
        self.assertEqual(self.state()["videos"]["v0"]["status"], st.POSTED)

    def test_dry_run_changes_nothing(self):
        self._seed("a.mp4")
        drive = FakeDrive([])
        with self.patch_drive(drive), mock.patch.object(app.Instagram, "publish_reel") as publish:
            self.assertEqual(app.run(replace(self.cfg, dry_run=True, ig_token=None)), 0)
        publish.assert_not_called()
        self.assertEqual(self.state()["videos"]["v0"]["status"], st.PENDING)


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
