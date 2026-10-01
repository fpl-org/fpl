"""tokview [--port N] [--root DIR]: serve the page on 127.0.0.1 and print its URL."""

import argparse
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path

from tokview.web import App, find_root, server


def main(
    argv: list[str] | None = None,
    run: Callable[[ThreadingHTTPServer], None] = ThreadingHTTPServer.serve_forever,
) -> None:
    """Parse argv, start the server, print its URL, and hand it to run (serve until killed)."""
    parser = argparse.ArgumentParser(prog="tokview", description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (8765)")
    parser.add_argument("--root", type=Path, help="the checkout whose features/ to list")
    args = parser.parse_args(argv)
    root: Path | None = args.root or find_root(Path(__file__).resolve())
    if root is None:
        parser.error("no features/ above the package; pass --root")
    httpd = server(App(root), args.port)
    print(f"tokview on http://127.0.0.1:{httpd.server_port}/", flush=True)
    run(httpd)


if __name__ == "__main__":
    main()
