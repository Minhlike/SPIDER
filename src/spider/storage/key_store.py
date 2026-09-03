"""Current-user Windows DPAPI storage. No portable/plaintext fallback."""
import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from pathlib import Path


class KeyStoreError(RuntimeError):
    def __init__(self):
        super().__init__("Protected settings unavailable; check the Windows account and local files.")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class WindowsDPAPI:
    """Bind ciphertext to the current Windows account, with UI disabled."""

    def _transform(self, content: bytes, decrypt: bool) -> bytes:
        if os.name != "nt":
            raise KeyStoreError()

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(content)
        source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        dest = Blob()
        func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        func.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        # CRYPTPROTECT_UI_FORBIDDEN, deliberately NOT CRYPTPROTECT_LOCAL_MACHINE.
        if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
            raise KeyStoreError()
        try:
            return ctypes.string_at(dest.data, dest.size)
        finally:
            ctypes.memset(dest.data, 0, dest.size)
            kernel.LocalFree(dest.data)
            ctypes.memset(buffer, 0, len(content))

    def protect(self, content: bytes) -> bytes:
        return self._transform(content, False)

    def unprotect(self, content: bytes) -> bytes:
        return self._transform(content, True)


class LocalKeyStore:
    def __init__(self, path: Path, protector=None):
        self.path = path
        self.protector = protector or WindowsDPAPI()

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            result = json.loads(self.protector.unprotect(self.path.read_bytes()))
            if not isinstance(result, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in result.items()
            ):
                raise KeyStoreError()
            return result
        except Exception:
            raise KeyStoreError() from None

    def save(self, keys: dict[str, str]) -> None:
        try:
            payload = json.dumps(keys).encode("utf-8")
            encrypted = self.protector.protect(payload)
            if self.protector.unprotect(encrypted) != payload:
                raise KeyStoreError()
            atomic_write(self.path, encrypted)
        except Exception:
            raise KeyStoreError() from None
