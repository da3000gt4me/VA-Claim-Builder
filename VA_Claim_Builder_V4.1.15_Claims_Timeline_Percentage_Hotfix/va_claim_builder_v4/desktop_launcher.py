from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "VA Claim Builder"
HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 120


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = root / "VA Claim Builder"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "VA Claim Builder"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "va-claim-builder"
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = user_data_dir()
LOG_PATH = DATA_DIR / "launcher.log"
STREAMLIT_LOG_PATH = DATA_DIR / "streamlit.log"


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
    except Exception:
        pass
    try:
        print(line, end="", flush=True)
    except Exception:
        pass


def free_port() -> int:
    log("Selecting an available localhost port...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        port = int(sock.getsockname()[1])
    log(f"Selected port: {port}")
    return port


def app_ready(url: str) -> bool:
    """Return True only when the actual Streamlit app page is mounted.

    The health endpoint alone is insufficient because Streamlit can be alive
    while the root application route still returns 404.
    """
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            body = response.read(8192).decode("utf-8", errors="ignore").lower()
            content_type = response.headers.get("Content-Type", "").lower()
            return (
                response.status == 200
                and "text/html" in content_type
                and ("streamlit" in body or "<!doctype html" in body)
            )
    except Exception:
        return False


def browser_worker(preferred_port: int) -> None:
    candidate_ports = []
    for candidate in (preferred_port, 8501, 3000):
        if candidate not in candidate_ports:
            candidate_ports.append(candidate)
    log(f"Browser monitor checking localhost ports: {candidate_ports}")
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for candidate in candidate_ports:
            url = f"http://{HOST}:{candidate}"
            if app_ready(url):
                log(f"Local server is ready at {url}; opening browser.")
                webbrowser.open(url, new=1, autoraise=True)
                return
        time.sleep(0.5)
    log(f"Browser monitor timed out after {STARTUP_TIMEOUT_SECONDS} seconds; no candidate port responded.")


def run_streamlit(app_path: Path, port: int) -> None:
    log("Preparing Streamlit CLI environment...")
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_ADDRESS"] = HOST
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_BROWSER_SERVER_ADDRESS"] = HOST
    os.environ["STREAMLIT_BROWSER_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "true"
    os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "true"
    os.environ["VCB_DATA_DIR"] = str(DATA_DIR / "data")

    url = f"http://{HOST}:{port}"
    thread = threading.Thread(target=browser_worker, args=(port,), daemon=True, name="browser-monitor")
    thread.start()

    # Use Streamlit's supported CLI path rather than its private bootstrap.run
    # interface. The private signature and initialization sequence vary across
    # Streamlit releases and can start a server without mounting the app route.
    log("Importing Streamlit CLI...")
    from streamlit.web import cli as streamlit_cli
    log("Streamlit CLI imported successfully.")

    cli_args = [
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode",
        "false",
        "--server.address",
        HOST,
        "--server.port",
        str(port),
        "--browser.serverAddress",
        HOST,
        "--browser.serverPort",
        str(port),
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
        "--server.enableCORS",
        "true",
        "--server.enableXsrfProtection",
        "true",
    ]
    log(f"Starting Streamlit through CLI on {url}")
    log(f"CLI arguments: {cli_args[1:]}")
    log(f"Streamlit diagnostics will be written to: {STREAMLIT_LOG_PATH}")

    previous_argv = sys.argv[:]
    with STREAMLIT_LOG_PATH.open("a", encoding="utf-8") as stream_log:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.argv = cli_args
            sys.stdout = stream_log
            sys.stderr = stream_log
            streamlit_cli.main()
        finally:
            sys.argv = previous_argv
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    log("Streamlit CLI returned normally.")


def main() -> None:
    try:
        log("=" * 72)
        log(f"Starting {APP_NAME} launcher version 4.1.9")
        log(f"Executable: {sys.executable}")
        log(f"Current working directory: {Path.cwd()}")
        log(f"Bundle root: {resource_path('.')}")
        app_path = resource_path("app.py")
        log(f"Application entry: {app_path}")
        log(f"Application entry exists: {app_path.is_file()}")
        if not app_path.is_file():
            raise FileNotFoundError(f"Packaged application entry file was not found: {app_path}")
        port = free_port()
        run_streamlit(app_path, port)
    except BaseException as exc:
        details = traceback.format_exc()
        log(f"Fatal launcher error: {exc!r}")
        log(details)
        try:
            with STREAMLIT_LOG_PATH.open("a", encoding="utf-8") as stream_log:
                stream_log.write(details)
                stream_log.flush()
        except Exception:
            pass
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"{exc}\n\nLogs:\n{LOG_PATH}\n{STREAMLIT_LOG_PATH}", APP_NAME, 0x10)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
