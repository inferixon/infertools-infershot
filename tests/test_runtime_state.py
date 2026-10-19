import importlib.util
import ctypes
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock


spec = importlib.util.spec_from_file_location("runtime_state", Path(__file__).parents[1] / "runtime_state.py")
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class RuntimeStateTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows kernel mutex integration")
    def test_real_session_mutex_is_released_and_can_be_reacquired(self):
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        api.CreateMutexW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        api.CloseHandle.restype = ctypes.c_int
        original = state.MUTEX_NAME
        state.MUTEX_NAME = "Local\\InfershotTest-" + uuid.uuid4().hex
        handle = None
        try:
            handle = state.acquire_session_mutex(api, ctypes.get_last_error)
            self.assertIsNotNone(handle)
            self.assertIsNone(state.acquire_session_mutex(api, ctypes.get_last_error))
            api.CloseHandle(handle)
            handle = state.acquire_session_mutex(api, ctypes.get_last_error)
            self.assertIsNotNone(handle)
        finally:
            if handle:
                api.CloseHandle(handle)
            state.MUTEX_NAME = original

    def test_users_and_sessions_have_independent_writable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [state.state_directory(session, Path(directory) / user)
                     for user in ("first", "second") for session in (1, 2)]
            self.assertEqual(len(set(paths)), 4)
            for pid, path in enumerate(paths, 10):
                state.write_pid(path / "infershot.pid", pid)
            for pid, path in enumerate(paths, 10):
                self.assertEqual((path / "infershot.pid").read_text(), str(pid))

    def test_cleanup_does_not_remove_another_process_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "infershot.pid"
            state.write_pid(path, 123)
            state.remove_owned_pid(path, 456)
            self.assertTrue(path.exists())
            state.remove_owned_pid(path, 123)
            self.assertFalse(path.exists())

    def test_duplicate_session_mutex_closes_extra_handle(self):
        api = Mock()
        api.CreateMutexW.return_value = 71
        self.assertIsNone(state.acquire_session_mutex(api, lambda: 183))
        api.CreateMutexW.assert_called_once_with(None, False, r"Local\INFERSHOT_SINGLE_INSTANCE")
        api.CloseHandle.assert_called_once_with(71)

    def test_new_mutex_is_retained_and_access_failure_is_not_a_duplicate(self):
        api = Mock()
        api.CreateMutexW.return_value = 72
        self.assertEqual(state.acquire_session_mutex(api, lambda: 0), 72)
        api.CloseHandle.assert_not_called()
        api.CreateMutexW.return_value = 0
        with self.assertRaises(OSError):
            state.acquire_session_mutex(api, lambda: 5)


if __name__ == "__main__":
    unittest.main()
