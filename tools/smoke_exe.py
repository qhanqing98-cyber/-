"""在真实 Windows 桌面检查打包程序，只操作本次启动的窗口与临时存档。"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
user = ctypes.WinDLL('user32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_Enum = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user.EnumWindows.argtypes = [_Enum, wintypes.LPARAM]
user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.IsWindow.argtypes = [wintypes.HWND]
user.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user.FindWindowW.restype = wintypes.HWND
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]


def windows():
    found = []
    @_Enum
    def collect(hwnd, data):
        title, name = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
        user.GetWindowTextW(hwnd, title, len(title))
        user.GetClassNameW(hwnd, name, len(name))
        if title.value == 'DeskPet' or name.value.startswith('DeskPetTray_'):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((hwnd, pid.value, title.value, name.value))
        return True
    user.EnumWindows(collect, 0)
    return found


def executable(pid):
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        path, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
            return Path(path.value).resolve()
    finally:
        kernel.CloseHandle(handle)


def until(predicate, description, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError(description)


def smoke():
    target = (ROOT / 'dist' / 'DeskPet.exe').resolve()
    if not user.FindWindowW('Shell_TrayWnd', None):
        raise RuntimeError('此检查需要真实 Windows 任务栏')
    if windows():
        raise RuntimeError('已有桌宠实例，请先自行退出，再运行此检查；不会操作现有实例')
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='exe-smoke-', dir=ROOT / 'build') as temporary:
        env = dict(os.environ, DESKPET_DATA_DIR=temporary)
        process = subprocess.Popen([str(target)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        owned = []
        try:
            def ready():
                if process.poll() is not None:
                    raise RuntimeError('本次启动的测试程序提前退出，未操作其他实例')
                current = [item for item in windows() if executable(item[1]) == target]
                owned[:] = current
                return current if any(item[2] == 'DeskPet' for item in current) and any(item[3].startswith('DeskPetTray_') for item in current) else None
            until(ready, '打包程序没有创建宠物和托盘窗口', timeout=40)
            pet_hwnd = next(item[0] for item in owned if item[2] == 'DeskPet')
            tray_hwnd = next(item[0] for item in owned if item[3].startswith('DeskPetTray_'))
            until(lambda: user.IsWindowVisible(pet_hwnd), '启动后宠物不可见')
            for visible in (False, True):
                assert user.PostMessageW(tray_hwnd, 0x8000 + 31, 0, (1 << 16) | 0x400)
                until(lambda: bool(user.IsWindowVisible(pet_hwnd)) == visible, '托盘隐藏/恢复未生效')
            def setting(key, expected):
                try:
                    saved = json.loads((Path(temporary) / 'settings.json').read_text(encoding='utf-8'))
                    return saved.get(key) == expected
                except (OSError, ValueError):
                    return False
            for quiet in (True, False):
                scan = user.MapVirtualKeyW(ord('Q'), 0)
                assert user.PostMessageW(pet_hwnd, 0x0100, ord('Q'), 1 | (scan << 16))
                assert user.PostMessageW(pet_hwnd, 0x0101, ord('Q'), 0xC0000001 | (scan << 16))
                until(lambda: setting('quiet', quiet), '安静模式或设置保存未生效')
            assert user.PostMessageW(tray_hwnd, 0x0010, 0, 0)
            assert process.wait(timeout=12) == 0
            until(lambda: all(not user.IsWindow(item[0]) for item in owned), '退出后仍有测试窗口')
            for filename in ('save.json', 'settings.json', 'words_index.json'):
                assert (Path(temporary) / filename).is_file(), filename
            log = Path(temporary) / 'crash.log'
            if log.exists():
                assert 'ERROR' not in log.read_text(encoding='utf-8'), '运行日志包含异常'
            print('PASS: packaged startup, native tray hide/show, quiet on/off, settings, clean exit')
        finally:
            if process.poll() is None:
                for hwnd, pid, title, name in owned:
                    if name.startswith('DeskPetTray_'):
                        user.PostMessageW(hwnd, 0x0010, 0, 0)
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    # 仅终止本检查明确启动、且未响应退出的进程。
                    process.terminate()
                    process.wait(timeout=8)


if __name__ == '__main__':
    smoke()
