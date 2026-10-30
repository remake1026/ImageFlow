import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from app.updater import UpdateCheckWorker, UpdateDownloadWorker, parse_release, version_tuple


def release():
    return {"tag_name": "v1.4.0", "body": "更新内容", "assets": [{
        "name": "ImageFlow-1.4.0-Windows-x86-x64-Setup.exe",
        "browser_download_url": "https://github.com/remake1026/ImageFlow/releases/download/v1.4.0/ImageFlow-1.4.0-Windows-x86-x64-Setup.exe",
        "digest": "sha256:" + "a" * 64, "size": 3,
    }]}


class UpdateTests(unittest.TestCase):
    def test_release_lookup_404_has_a_separate_result(self):
        worker = UpdateCheckWorker("1.3.0")
        missing, failures = [], []
        worker.release_not_found.connect(lambda: missing.append(True))
        worker.failed.connect(failures.append)
        with patch("app.updater._request", side_effect=HTTPError("https://api.github.com", 404, "Not Found", {}, None)):
            worker.run()
        self.assertEqual(missing, [True])
        self.assertEqual(failures, [])

    def test_other_http_errors_remain_failures(self):
        worker = UpdateCheckWorker("1.3.0")
        missing, failures = [], []
        worker.release_not_found.connect(lambda: missing.append(True))
        worker.failed.connect(failures.append)
        with patch("app.updater._request", side_effect=HTTPError("https://api.github.com", 403, "Forbidden", {}, None)):
            worker.run()
        self.assertEqual(missing, [])
        self.assertEqual(len(failures), 1)

    def test_version_and_release_validation(self):
        self.assertGreater(version_tuple("1.10.0"), version_tuple("1.9.0"))
        self.assertIsNone(parse_release(release(), "1.4.0"))
        self.assertEqual(parse_release(release(), "1.3.0")["version"], "1.4.0")
        data = release()
        data["assets"][0]["digest"] = None
        with self.assertRaises(ValueError):
            parse_release(data, "1.3.0")
        data = release()
        data["assets"][0]["browser_download_url"] = "https://example.com/setup.exe"
        with self.assertRaises(ValueError):
            parse_release(data, "1.3.0")

    def test_bad_download_is_rejected(self):
        from io import BytesIO
        worker = UpdateDownloadWorker(parse_release(release(), "1.3.0"))
        failures, results = [], []
        worker.failed.connect(failures.append)
        worker.result.connect(results.append)
        with patch("app.updater._request", return_value=BytesIO(b"bad")):
            worker.run()
        self.assertEqual(len(failures), 1)
        self.assertEqual(results, [])
