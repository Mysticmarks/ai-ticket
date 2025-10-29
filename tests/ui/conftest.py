import contextlib
import os
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

import pytest


class SPARequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - inherited signature
        # Silence server logs during tests to keep output tidy.
        return

    def send_head(self):  # type: ignore[override]
        # The default implementation raises 404 for unknown routes, but SPA routing expects index.html.
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            index_path = os.path.join(path, "index.html")
            if os.path.exists(index_path):
                path = index_path
        if not os.path.exists(path):
            path = os.path.join(self.directory or "", "index.html")

        ctype = self.guess_type(path)
        try:
            with open(path, "rb") as file:  # noqa: PTH123 - serving static files
                self.send_response(200)
                self.send_header("Content-type", ctype)
                fs = os.fstat(file.fileno())
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()
                return file
        except OSError:
            self.send_error(404, "File not found")
            return None


class ThreadedTCPServer(TCPServer):
    allow_reuse_address = True


@pytest.fixture(scope="session")
def dashboard_dist() -> Path:
    dist = Path(__file__).resolve().parents[2] / "src" / "ai_ticket" / "ui" / "dist"
    if not dist.exists():
        pytest.skip("Dashboard bundle is missing. Run `npm run build` in src/ai_ticket/ui first.")
    return dist


@pytest.fixture(scope="session")
def dashboard_server(dashboard_dist: Path):
    handler = lambda *args, **kwargs: SPARequestHandler(*args, directory=str(dashboard_dist), **kwargs)
    server = ThreadedTCPServer(("127.0.0.1", 0), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        with contextlib.suppress(Exception):
            server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def screenshot_dir() -> Path:
    output_dir = Path(__file__).parent / "__screenshots__"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
