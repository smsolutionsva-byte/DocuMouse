"""Run a password-protected Windows test site through a Cloudflare Quick Tunnel."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOCAL = ROOT / ".local-hosting"
STATE = LOCAL / "processes.json"
CODE = LOCAL / "access-code.txt"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
API = "http://127.0.0.1:8787"
WEB = "http://127.0.0.1:3176"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def request_status(url: str, headers: dict | None = None) -> int:
    try:
        with build_opener(NoRedirect).open(Request(url, headers=headers or {}), timeout=5) as response:
            return response.status
    except HTTPError as error:
        return error.code
    except (URLError, TimeoutError, OSError):
        return 0


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found and name in ("cloudflared", "uv"):
        fallback = (
            Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe"
            if name == "cloudflared"
            else Path.home() / ".local" / "bin" / "uv.exe"
        )
        if fallback.is_file():
            found = str(fallback)
    if not found:
        raise RuntimeError(f"{name} is missing. See docs/pc-test-site.md.")
    return found


def process_for(record: dict):
    import psutil

    try:
        process = psutil.Process(record["pid"])
        if (
            process.is_running()
            and process.create_time() == record["created"]
            and process.exe() == record["exe"]
            and process.cmdline() == record["args"]
        ):
            return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"processes": []}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def stop(state: dict | None = None) -> None:
    import psutil

    state = state if state is not None else load_state()
    owned = []
    for record in reversed(state["processes"]):
        process = process_for(record)
        if process is None:
            continue
        try:
            owned.extend(process.children(recursive=True))
        except psutil.NoSuchProcess:
            continue
        owned.append(process)
    for process in owned:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(owned, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    if LOCAL.exists():
        save_state({"processes": []})
    print("Test-site processes stopped. Documents and access code were preserved.")


def start_process(role: str, args: list[str], cwd: Path, env: dict, state: dict) -> None:
    import psutil

    with (LOCAL / f"{role}.out.log").open("w", encoding="utf-8") as stdout:
        with (LOCAL / f"{role}.err.log").open("w", encoding="utf-8") as stderr:
            child = subprocess.Popen(
                args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
    process = psutil.Process(child.pid)
    state["processes"].append({
        "role": role, "pid": child.pid, "created": process.create_time(),
        "exe": process.exe(), "args": process.cmdline(),
    })
    save_state(state)


def wait_for_service(url: str, state: dict, expected: int = 200) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not all(process_for(record) for record in state["processes"]):
            raise RuntimeError(f"A service exited. Check logs in {LOCAL}.")
        if request_status(url) == expected:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Service did not become ready: {url}. Check logs in {LOCAL}.")


def setup() -> None:
    uv = executable("uv")
    if not PYTHON.exists():
        subprocess.run([uv, "venv", "--python", "3.12", str(BACKEND / ".venv")], check=True)
    subprocess.run([uv, "pip", "install", "--python", str(PYTHON), "-e", ".[ocr,hosting]"], cwd=BACKEND, check=True)
    npm = executable("npm.cmd")
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    env = dict(os.environ, DOCUMOUSE_API_URL=API, NEXT_PUBLIC_DOCUMOUSE_UPLOAD_URL="")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, env=env, check=True)
    executable("cloudflared")
    print("PC hosting dependencies and production frontend are ready.")


def start() -> None:
    if not PYTHON.is_file():
        raise RuntimeError("Run setup first.")
    state = load_state()
    if any(process_for(record) for record in state["processes"]):
        raise RuntimeError("Test-site processes already exist. Use status or stop before starting again.")
    for port in (8787, 3176):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(f"Local port {port} is already in use; its process was left alone.") from error
    standalone = FRONTEND / ".next" / "standalone"
    if not (standalone / "server.js").is_file():
        raise RuntimeError("Production frontend is missing. Run setup first.")
    manifest = json.loads((FRONTEND / ".next" / "routes-manifest.json").read_text(encoding="utf-8"))
    rewrites = manifest["rewrites"]
    if isinstance(rewrites, dict):
        rewrites = [rule for group in rewrites.values() for rule in group]
    if not any(rule.get("destination") == f"{API}/api/:path*" for rule in rewrites):
        raise RuntimeError("Frontend was built for a different API address. Run setup first.")
    shutil.copytree(FRONTEND / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    if (FRONTEND / "public").is_dir():
        shutil.copytree(FRONTEND / "public", standalone / "public", dirs_exist_ok=True)
    LOCAL.mkdir(exist_ok=True)
    (LOCAL / "data").mkdir(exist_ok=True)
    if not CODE.exists():
        CODE.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")
    token = CODE.read_text(encoding="utf-8").strip()
    if len(token) < 24 or any(char.isspace() for char in token):
        raise RuntimeError("Access code must contain at least 24 characters and no whitespace.")
    env = dict(
        os.environ, DOCUMOUSE_AUTH_TOKEN=token,
        DOCUMOUSE_DATABASE_URL=f"sqlite:///{(LOCAL / 'documouse.db').as_posix()}",
        DOCUMOUSE_STORAGE_DIR=str(LOCAL / "data"), DOCUMOUSE_STORAGE_BACKEND="local",
        DOCUMOUSE_OCR_DEVICE="cpu", DOCUMOUSE_OCR_PRESET="fast", DOCUMOUSE_PROCESSING_WORKERS="1",
        DOCUMOUSE_LLM_PROVIDER="none", DOCUMOUSE_SECOND_READER="none",
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True", PYTHONUNBUFFERED="1",
        UVICORN_RELOAD="false", WEB_CONCURRENCY="1",
        NODE_ENV="production", PORT="3176", HOSTNAME="127.0.0.1",
    )
    state = {"processes": []}
    try:
        start_process("backend", [str(PYTHON), "-m", "uvicorn", "documouse.main:app", "--host", "127.0.0.1", "--port", "8787", "--workers", "1", "--no-server-header"], BACKEND, env, state)
        wait_for_service(f"{API}/api/health", state)
        if request_status(f"{API}/api/documents/stats") != 401:
            raise RuntimeError("Backend did not reject an anonymous request; tunnel was not opened.")
        if request_status(f"{API}/api/documents/stats", {"Authorization": f"Bearer {token}"}) != 200:
            raise RuntimeError("Backend did not accept its access code; tunnel was not opened.")
        start_process("frontend", [executable("node"), "server.js"], standalone, env, state)
        wait_for_service(f"{WEB}/login", state)
        if request_status(WEB) != 307:
            raise RuntimeError("Frontend did not redirect an anonymous visitor to login; tunnel was not opened.")
        start_process("tunnel", [executable("cloudflared"), "tunnel", "--protocol", "http2", "--url", WEB], ROOT, dict(os.environ), state)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not all(process_for(record) for record in state["processes"]):
                raise RuntimeError(f"A service exited. Check logs in {LOCAL}.")
            logs = (LOCAL / "tunnel.err.log").read_text(encoding="utf-8", errors="replace")
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", logs)
            if match:
                state["url"] = match.group()
                save_state(state)
                print(f"Test website: {state['url']}")
                print(f"Private access code: {CODE}")
                print("Keep this PC awake. Stopping or restarting the tunnel changes its public URL.")
                return
            time.sleep(0.5)
        raise RuntimeError(f"Cloudflare did not return a URL. Check logs in {LOCAL}.")
    except BaseException:
        stop(state)
        raise


def status() -> None:
    state = load_state()
    for record in state["processes"]:
        print(f"{record['role']}: {'running' if process_for(record) else 'stopped'}")
    if state.get("url"):
        print(f"Test website: {state['url']}")
    if not state["processes"]:
        print("Test site is stopped.")
    if CODE.exists():
        print(f"Private access code: {CODE}")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This launcher is for Windows. Use docs/hosting.md for a Linux server.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "start", "status", "stop"))
    args = parser.parse_args()
    {"setup": setup, "start": start, "status": status, "stop": stop}[args.action]()


if __name__ == "__main__":
    main()
