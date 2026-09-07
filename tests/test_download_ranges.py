from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from download_models_ranged import get_part


class DownloadRangeTests(unittest.TestCase):
    def test_resumes_existing_prefix_with_exact_range(self):
        payload = b"the complete verified byte sequence"
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start, end = map(int, self.headers["Range"][6:].split("-"))
                seen.append((start, end))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                self.wfile.write(payload[start:end + 1])

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                part = Path(directory) / "000.part"
                part.with_suffix(".partial").write_bytes(payload[:7])
                size = get_part((f"http://127.0.0.1:{server.server_port}/file", part, 0, len(payload) - 1, len(payload)))
                self.assertEqual(size, len(payload))
                self.assertEqual(part.read_bytes(), payload)
                self.assertEqual(seen, [(7, len(payload) - 1)])
            finally:
                server.shutdown()
                thread.join()

    def test_rejects_server_that_ignores_range_without_damaging_prefix(self):
        with tempfile.TemporaryDirectory() as directory, patch("download_models_ranged.requests.get") as get, patch("download_models_ranged.time.sleep"):
            part = Path(directory) / "000.part"
            prefix = part.with_suffix(".partial")
            prefix.write_bytes(b"abc")
            response = get.return_value.__enter__.return_value
            response.status_code = 200
            response.headers = {}
            with self.assertRaisesRegex(RuntimeError, "Invalid range response"):
                get_part(("http://example.invalid/file", part, 0, 9, 10))
            self.assertEqual(prefix.read_bytes(), b"abc")
            self.assertFalse(part.exists())


if __name__ == "__main__":
    unittest.main()
