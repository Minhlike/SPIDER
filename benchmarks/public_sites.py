"""Identical synthetic HTTP responses for all username engines."""
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# Unknown cases are not scored as negatives: access is insufficient to decide.
TRUTH = {"Present": True, "Absent": False, "SoftAbsent": False,
         "Blocked": None, "RateLimited": None, "Slow": None, "Wildcard": False}


@contextmanager
def public_sites(folder, names=None):
    names = list(names or TRUTH)
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            name = self.path.split("/")[1]
            requests.append(name)
            code = {"Absent": 404, "Blocked": 403, "RateLimited": 429}.get(name, 200)
            if name == "Present" and self.path.rsplit("/", 1)[-1] != "fixture-user": code = 404
            body = (b'<html><head><meta property="og:title" content="Fixture Public Name">'
                    b'<meta property="og:description" content="Public fixture biography"></head>'
                    b'<body>PROFILE_PRESENT</body></html>') if name == "Present" else b"PROFILE_ABSENT"
            if name == "Slow": time.sleep(5)
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        do_HEAD = do_GET
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    maigret, sherlock = {}, {}
    for index, name in enumerate(names):
        url = f"{base}/{name}/{{username}}"
        maigret[name] = {"url": url, "urlMain": base, "checkType": "message" if name == "SoftAbsent" else "status_code",
            "presenseStrs": ["PROFILE_PRESENT"], "absenceStrs": ["PROFILE_ABSENT"], "alexaRank": index+1,
            "usernameClaimed": "fixture-user", "usernameUnclaimed": "fixture-missing"}
        sherlock[name] = {"url": url.replace("{username}", "{}"), "urlMain": base,
            "errorType": "message" if name == "SoftAbsent" else "status_code",
            "errorMsg": "PROFILE_ABSENT", "username_claimed": "fixture-user",
            "username_unclaimed": "fixture-missing"}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    db = folder / "maigret-sites.json"
    db.write_text(json.dumps({"sites": maigret}), encoding="utf-8")
    other = folder / "sherlock-sites.json"
    other.write_text(json.dumps(sherlock), encoding="utf-8")
    try:
        yield {"maigret": db, "sherlock": other, "base_url": base, "requests": requests,
               "truth": {name: TRUTH[name] for name in names}}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
