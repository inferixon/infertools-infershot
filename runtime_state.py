"""Per-user, per-Windows-session state without importing the capture UI."""

import ctypes
import os
from pathlib import Path
import tempfile


MUTEX_NAME = r"Local\INFERSHOT_SINGLE_INSTANCE"


def current_session_id(api, process_id=None):
    session = ctypes.c_ulong()
    if not api.ProcessIdToSessionId(process_id or os.getpid(), ctypes.byref(session)):
        raise OSError("Cannot determine the Windows session for Infershot")
    return session.value


def state_directory(session_id, local_app_data=None):
    if not isinstance(session_id, int) or session_id < 0:
        raise ValueError("Windows session ID must be a non-negative integer")
    root = local_app_data or os.environ.get("LOCALAPPDATA")
    if not root:
        root = Path.home() / "AppData" / "Local"
    return Path(root) / "Infershot" / "sessions" / str(session_id)


def acquire_session_mutex(api, last_error):
    handle = api.CreateMutexW(None, False, MUTEX_NAME)
    error = last_error()
    if not handle:
        raise OSError(error, "Cannot create the Infershot session mutex")
    if error == 183:  # ERROR_ALREADY_EXISTS
        api.CloseHandle(handle)
        return None
    return handle


def write_pid(path, process_id):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="infershot-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(str(process_id))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def remove_owned_pid(path, process_id):
    path = Path(path)
    try:
        if path.read_text(encoding="ascii").strip() == str(process_id):
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
