"""Tests for the upload step. No network and no real password: curl is replaced by a fake."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from watcher import run as runmod
from watcher.publish import PublishError, publish_page, upload, verify

CFG = {"host": "example.org", "user": "me", "remote_path": "/home/me/site/page.html",
       "public_url": "https://example.org/page.html", "hostkey_sha256": "PIN=", "curl": "curl"}
SECRET = "p@ss" + chr(34) + "word" + chr(92) + "1"  # p@ss"word: a quote and a backslash


class Recorder:
    def __init__(self, rc=0, stderr=""):
        self.calls, self.rc, self.stderr = [], rc, stderr

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        return SimpleNamespace(returncode=self.rc, stdout="", stderr=self.stderr)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Path(self.tmp.name) / "page.html"
        self.f.write_text("<html>hi</html>", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_goes_on_stdin_never_on_the_command_line(self):
        r = Recorder()
        upload(self.f, CFG, secret=SECRET, runner=r)
        cmd, kw = r.calls[0]
        self.assertNotIn(SECRET, " ".join(cmd))
        self.assertNotIn("me:", " ".join(cmd))
        self.assertIn("-K", cmd)
        self.assertTrue(kw["input"].startswith('user = "me:'))
        self.assertIn("p@ss" + chr(92) + chr(34) + "word" + chr(92) + chr(92) + "1", kw["input"])  # quote and backslash escaped for curl's config format

    def test_host_key_is_pinned_and_target_url_is_right(self):
        r = Recorder()
        upload(self.f, CFG, secret=SECRET, runner=r)
        cmd = r.calls[0][0]
        self.assertEqual(cmd[cmd.index("--hostpubsha256") + 1], "PIN=")
        self.assertEqual(cmd[-1], "sftp://example.org/home/me/site/page.html.part")  # temp name first
        qs = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-Q"]
        self.assertEqual(qs, ["-*RM /home/me/site/page.html", "-RENAME /home/me/site/page.html.part /home/me/site/page.html"])

    def test_no_pinned_key_means_no_upload(self):
        r = Recorder()
        with self.assertRaises(PublishError):
            upload(self.f, {k: v for k, v in CFG.items() if k != "hostkey_sha256"}, secret=SECRET, runner=r)
        self.assertEqual(r.calls, [])

    def test_missing_password_means_no_upload(self):
        r = Recorder()
        with mock.patch("watcher.publish.get_secret", return_value=""):
            with self.assertRaises(PublishError):
                upload(self.f, CFG, runner=r)
        self.assertEqual(r.calls, [])

    def test_failure_message_never_contains_the_password(self):
        r = Recorder(rc=67, stderr=f"Login denied for {SECRET}")
        with self.assertRaises(PublishError) as cm:
            upload(self.f, CFG, secret=SECRET, runner=r)
        self.assertNotIn(SECRET, str(cm.exception))
        self.assertIn("exit 67", str(cm.exception))

    def test_verify_requires_http_200_and_identical_bytes(self):
        data = self.f.read_bytes()
        verify(self.f, CFG["public_url"], fetcher=lambda u: (200, data))
        with self.assertRaises(PublishError):
            verify(self.f, CFG["public_url"], fetcher=lambda u: (200, b"old page"))
        with self.assertRaises(PublishError):
            verify(self.f, CFG["public_url"], fetcher=lambda u: (404, data))

    def test_upload_can_target_another_file_next_to_the_page(self):
        r = Recorder()
        upload(self.f, CFG, secret=SECRET, runner=r, remote_path="/home/me/site/preview.png")
        cmd = r.calls[0][0]
        self.assertEqual(cmd[-1], "sftp://example.org/home/me/site/preview.png.part")
        self.assertIn("-RENAME /home/me/site/preview.png.part /home/me/site/preview.png", cmd)

    def test_child_environment_has_no_password_variable(self):
        r = Recorder()
        with mock.patch.dict("os.environ", {"DH_PASS": "secret-value", "KEEP": "1"}):
            upload(self.f, CFG, secret=SECRET, runner=r)
        env = r.calls[0][1]["env"]
        self.assertNotIn("DH_PASS", env)
        self.assertEqual(env.get("KEEP"), "1")

    def test_mismatch_triggers_one_re_upload_then_succeeds(self):
        r = Recorder()
        answers = iter([(200, b"half written"), (200, self.f.read_bytes())])
        publish_page(self.f, CFG, secret=SECRET, runner=r, fetcher=lambda u: next(answers))
        self.assertEqual(len(r.calls), 2)

    def test_mismatch_twice_raises(self):
        r = Recorder()
        with self.assertRaises(PublishError):
            publish_page(self.f, CFG, secret=SECRET, runner=r, fetcher=lambda u: (200, b"still wrong"))
        self.assertEqual(len(r.calls), 2)

    def test_publish_page_uploads_then_verifies(self):
        r = Recorder()
        publish_page(self.f, CFG, secret=SECRET, runner=r, fetcher=lambda u: (200, self.f.read_bytes()))
        self.assertEqual(len(r.calls), 1)


class RunIntegrationTests(unittest.TestCase):
    FEED = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a1</id>'
            '<title>The White House Accord explained</title><link href="https://e.com/1"/>'
            '<published>2026-10-03T08:00:00Z</published></entry></feed>')

    def _run(self, td, publish_cfg, side_effect=None):
        import json
        d = Path(td)
        (d / "s.json").write_text(json.dumps([{"id": "s", "label": "S", "type": "feed", "url": "u"}]), encoding="utf-8")
        (d / "r.json").write_text(json.dumps({"strong": ["White House Accord"], "weak": [], "notify_cap": 5}), encoding="utf-8")
        local = {"labchan_dir": str(d)}
        if publish_cfg:
            local["publish"] = publish_cfg
        (d / "l.json").write_text(json.dumps(local), encoding="utf-8")
        args = ["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--local", str(d / "l.json"),
                "--state", str(d / "seen.json"), "--captured", str(d / "cap"), "--page", str(d / "p.html"), "--live"]
        with mock.patch.object(runmod, "fetch", lambda url: (self.FEED, url)), \
             mock.patch.object(runmod, "send_labchan") as lab, \
             mock.patch.object(runmod, "send_email", return_value=False), \
             mock.patch.object(runmod, "capture", return_value=(d / "x.md", True)), \
             mock.patch.object(runmod, "publish_page", side_effect=side_effect) as pub:
            runmod.main(args)
        return lab, pub

    def test_no_publish_settings_means_no_upload(self):
        with tempfile.TemporaryDirectory() as td:
            _, pub = self._run(td, None)
            pub.assert_not_called()

    def test_live_run_publishes_the_page_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            _, pub = self._run(td, CFG)
            self.assertEqual(pub.call_count, 1)
            self.assertTrue(str(pub.call_args[0][0]).endswith("p.html"))

    def test_upload_failures_alert_once_on_the_third_run_in_a_row(self):
        with tempfile.TemporaryDirectory() as td:
            alerts = []
            for _ in range(4):
                lab, _ = self._run(td, CFG, side_effect=PublishError("upload failed (curl exit 7)"))
                alerts.append(any("upload failed" in str(c) for c in lab.call_args_list))
            self.assertEqual(alerts, [False, False, True, False])


if __name__ == "__main__":
    unittest.main()
