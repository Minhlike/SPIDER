"""Opaque, process-local cursors for bounded investigation reads.

The cursor is integrity protected so an agent cannot replay it against another
case, seed, question, or read surface.  It intentionally contains no source
content, credential, or raw artifact reference.  A process restart expires old
cursors; callers can request a new snapshot rather than receiving mixed pages.
"""
import base64
import hashlib
import hmac
import json
import secrets


_KEY = secrets.token_bytes(32)


def _pack(payload):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_KEY, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode("ascii").rstrip("=")


def _unpack(token):
    if not isinstance(token, str) or len(token) > 2048:
        raise ValueError("Invalid read cursor")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        body, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.new(_KEY, body, hashlib.sha256).digest()):
            raise ValueError("Invalid read cursor")
        value = json.loads(body)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise ValueError("Invalid read cursor") from None
    if not isinstance(value, dict) or value.get("v") != 1:
        raise ValueError("Invalid read cursor")
    return value


def make_snapshot(surface, case_id, target_id, question, bounds):
    return _pack({"v": 1, "surface": surface, "case": case_id, "target": target_id,
                  "question": question, "bounds": bounds})


def read_snapshot(token, surface, case_id, target_id, question):
    value = _unpack(token)
    if (value.get("surface"), value.get("case"), value.get("target"), value.get("question")) != (
            surface, case_id, target_id, question):
        raise ValueError("Cursor outside selected scope")
    bounds = value.get("bounds")
    if not isinstance(bounds, dict):
        raise ValueError("Invalid read cursor")
    return bounds


def make_cursor(snapshot, position):
    return _pack({"v": 1, "snapshot": snapshot, "position": position})


def read_cursor(token, snapshot):
    value = _unpack(token)
    if value.get("snapshot") != snapshot or not isinstance(value.get("position"), str):
        raise ValueError("Cursor outside selected snapshot")
    return value["position"]
