"""Windows single-instance launcher. Uses a shutdown event, never taskkill."""
import argparse
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import uuid
import webbrowser

from spider.storage.key_store import atomic_write

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "runtime/venv/Scripts/python.exe"
DATA = ROOT / "data"
STATE = DATA / "launcher.json"
URL = "http://127.0.0.1:8765"


def winapi():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateEventW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "OpenEventW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
        "QueryFullProcessImageNameW": ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                        ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        getattr(kernel, name).argtypes = args
        getattr(kernel, name).restype = result
    return kernel


def process_identity(pid):
    """PID + creation time + executable identify an exact process instance."""
    kernel = winapi()
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, int(pid))
    if not handle:
        return None
    try:
        if kernel.WaitForSingleObject(handle, 0) != 258:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return None
        return {"pid": int(pid), "created": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                "image": image.value.casefold()}
    finally:
        kernel.CloseHandle(handle)


def read_state():
    try:
        state = json.loads(STATE.read_text())
        expected = {k: state[k] for k in ("pid", "created", "image")}
        if state["root"] == str(ROOT) and process_identity(state["pid"]) == expected:
            return state
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


@contextmanager
def launcher_lock():
    import msvcrt
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "launcher.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + 60
        while True:
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another launcher is busy. Try again shortly.") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def healthy():
    try:
        with urlopen(URL + "/api/health?ready=true", timeout=2) as response:
            health = json.load(response)
            state = read_state()
            return bool(state and health.get("status") == "HEALTHY" and health.get("pid") == state["pid"])
    except Exception:
        return False


def port_available():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", 8765))
            return True
        except OSError:
            return False


def signal_stop(state):
    if read_state() != state:
        raise RuntimeError("Backend identity changed; no process was signalled.")
    kernel = winapi()
    event = kernel.OpenEventW(2, False, state["stop_event"])
    if not event:
        raise RuntimeError("Shutdown event unavailable; no process was killed.")
    try:
        if not kernel.SetEvent(event):
            raise RuntimeError("Unable to request shutdown.")
    finally:
        kernel.CloseHandle(event)


def start(open_browser=True):
    with launcher_lock():
        state = read_state()
        if not state:
            if not port_available():
                raise RuntimeError("Port 8765 is occupied by an unmanaged process; it was left untouched.")
            if not PYTHON.exists():
                raise RuntimeError("Project-local Python runtime is missing.")
            nonce = uuid.uuid4().hex
            with (DATA / "launcher.log").open("ab") as log:
                process = subprocess.Popen(
                    [str(PYTHON), "-m", "spider.launcher", "serve", "--nonce", nonce],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                state = read_state()
                if state and state.get("nonce") == nonce and healthy():
                    break
                if process.poll() is not None:
                    raise RuntimeError("Backend exited during startup; see data/launcher.log.")
                time.sleep(0.3)
            else:
                if state and state.get("nonce") == nonce:
                    signal_stop(state)
                raise RuntimeError("Health check timed out; shutdown requested. See data/launcher.log.")
        elif not healthy():
            raise RuntimeError("Tracked backend is not healthy; use stop_spider.bat before retrying.")
        print(f"SPIDER ready: {URL} (backend PID {state['pid']})")
        if open_browser:
            webbrowser.open(URL)
        return state


def stop():
    with launcher_lock():
        state = read_state()
        if not state:
            print("No verified SPIDER backend. No process was stopped.")
            return
        signal_stop(state)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process_identity(state["pid"]) != {k: state[k] for k in ("pid", "created", "image")}:
                print(f"SPIDER stopped cleanly (PID {state['pid']}).")
                return
            time.sleep(0.2)
        raise RuntimeError("Shutdown still pending; no forced kill was performed. See data/launcher.log.")


def serve(nonce):
    import uvicorn
    os.chdir(ROOT)
    kernel = winapi()
    event_name = "Local\\SPIDER-stop-" + nonce
    event = kernel.CreateEventW(None, True, False, event_name)
    if not event:
        raise RuntimeError("Cannot create shutdown event.")
    state = {**process_identity(os.getpid()), "root": str(ROOT), "stop_event": event_name, "nonce": nonce}
    server = uvicorn.Server(uvicorn.Config("spider.web.app:create_app", factory=True,
                                         host="127.0.0.1", port=8765, access_log=False,
                                         timeout_graceful_shutdown=30))
    finished = threading.Event()
    def watch_stop():
        while not finished.is_set():
            if kernel.WaitForSingleObject(event, 250) == 0:
                server.should_exit = True
                return
    watcher = threading.Thread(target=watch_stop, daemon=True)
    try:
        atomic_write(STATE, json.dumps(state).encode())
        atomic_write(DATA / "spider.pid", str(os.getpid()).encode())
        watcher.start()
        server.run()
    finally:
        finished.set()
        watcher.join(timeout=1)
        kernel.CloseHandle(event)
        if read_state() == state:
            STATE.unlink(missing_ok=True)
            (DATA / "spider.pid").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "serve"])
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--nonce")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This launcher requires Windows.")
    try:
        if args.action == "start":
            start(not args.no_browser)
        elif args.action == "stop":
            stop()
        elif args.nonce:
            serve(args.nonce)
        else:
            parser.error("Internal serve invocation requires a nonce.")
    except Exception as error:
        print(f"SPIDER: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
