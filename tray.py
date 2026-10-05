"""原生 Windows 托盘。回调只排队动作，主循环负责修改宠物和设置。"""
from collections import deque
import ctypes
from ctypes import wintypes
import uuid
import time

import numpy as np
import pygame

from storage import log
from window import _BITMAPINFO, _DIB_RGB_COLORS

_user32 = ctypes.WinDLL('user32', use_last_error=True)
_shell32 = ctypes.WinDLL('shell32', use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
_CALLBACK = 0x8000 + 31
_HOTKEY = 1
_WndProc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class _WNDCLASS(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', _WndProc),
                ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HANDLE), ('hIcon', wintypes.HANDLE),
                ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HANDLE),
                ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]


class _GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                ('Data3', wintypes.WORD), ('Data4', wintypes.BYTE * 8)]


class _NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND),
                ('uID', wintypes.UINT), ('uFlags', wintypes.UINT),
                ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HANDLE),
                ('szTip', wintypes.WCHAR * 128), ('dwState', wintypes.DWORD),
                ('dwStateMask', wintypes.DWORD), ('szInfo', wintypes.WCHAR * 256),
                ('uVersion', wintypes.UINT), ('szInfoTitle', wintypes.WCHAR * 64),
                ('dwInfoFlags', wintypes.DWORD), ('guidItem', _GUID),
                ('hBalloonIcon', wintypes.HANDLE)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [('fIcon', wintypes.BOOL), ('xHotspot', wintypes.DWORD),
                ('yHotspot', wintypes.DWORD), ('hbmMask', wintypes.HBITMAP),
                ('hbmColor', wintypes.HBITMAP)]


_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HANDLE
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASS)]
_user32.RegisterClassW.restype = wintypes.WORD
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE]
_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HANDLE, ctypes.c_void_p]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT, wintypes.UINT]
_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype = ctypes.c_ssize_t
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.CreatePopupMenu.restype = wintypes.HMENU
_user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
_user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
_user32.TrackPopupMenu.restype = wintypes.UINT
_user32.DestroyMenu.argtypes = [wintypes.HMENU]
_user32.CreateIconIndirect.argtypes = [ctypes.POINTER(_ICONINFO)]
_user32.CreateIconIndirect.restype = wintypes.HANDLE
_user32.DestroyIcon.argtypes = [wintypes.HANDLE]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                  ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
_gdi32.CreateBitmap.restype = wintypes.HBITMAP
_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
_shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATA)]


def _create_pet_icon(sprite):
    """从表现层画布创建托盘图标；位图用完立即释放，不生成临时文件。"""
    side = 32
    scale = min(28 / sprite.get_width(), 28 / sprite.get_height())
    image = pygame.transform.smoothscale(sprite, (max(1, round(sprite.get_width() * scale)),
                                                  max(1, round(sprite.get_height() * scale))))
    canvas = pygame.Surface((side, side), pygame.SRCALPHA)
    canvas.blit(image, image.get_rect(center=(16, 16)))
    arr = np.frombuffer(pygame.image.tobytes(canvas, 'BGRA'), np.uint8).reshape(side, side, 4).copy()
    arr[:, :, :3] = (arr[:, :, :3].astype(np.uint16) * arr[:, :, 3:4] // 255).astype(np.uint8)
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
    bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = side, -side
    bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
    bits = ctypes.c_void_p()
    dc = _user32.GetDC(None)
    bitmap = mask = None
    try:
        bitmap = _gdi32.CreateDIBSection(dc, ctypes.byref(bmi), _DIB_RGB_COLORS,
                                        ctypes.byref(bits), None, 0)
        if not bitmap or not bits:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(bits, arr.tobytes(), side * side * 4)
        mask_bits = ctypes.create_string_buffer(bytes(side * side // 8))
        mask = _gdi32.CreateBitmap(side, side, 1, 1, mask_bits)
        if not mask:
            raise ctypes.WinError(ctypes.get_last_error())
        icon = _user32.CreateIconIndirect(ctypes.byref(_ICONINFO(True, 0, 0, mask, bitmap)))
        if not icon:
            raise ctypes.WinError(ctypes.get_last_error())
        return icon
    finally:
        if bitmap:
            _gdi32.DeleteObject(bitmap)
        if mask:
            _gdi32.DeleteObject(mask)
        _user32.ReleaseDC(None, dc)


class TrayIcon:
    def __init__(self, sprite):
        self.hwnd = self.icon = None
        self._nid = None
        self._registered = self._class_registered = False
        self.hotkey_registered = False
        self._next_retry = 0.0
        self._actions = deque()
        self._state = {}
        self._class_name = 'DeskPetTray_' + uuid.uuid4().hex
        self._instance = _kernel32.GetModuleHandleW(None)
        self._taskbar_created = _user32.RegisterWindowMessageW('TaskbarCreated')
        self._proc = _WndProc(self._wnd_proc)  # 强引用，防止原生回调被回收。
        try:
            wc = _WNDCLASS()
            wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = self._proc, self._instance, self._class_name
            if not _user32.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._class_registered = True
            self.hwnd = _user32.CreateWindowExW(0, self._class_name, 'DeskPet Tray',
                                               0, 0, 0, 0, 0, None, None, self._instance, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self.icon = _create_pet_icon(sprite)
            self._nid = _NOTIFYICONDATA()
            self._nid.cbSize = ctypes.sizeof(_NOTIFYICONDATA)
            self._nid.hWnd, self._nid.uID = self.hwnd, 1
            self._nid.uFlags = 0x01 | 0x02 | 0x04 | 0x80  # 回调、图标、提示、标准提示。
            self._nid.uCallbackMessage, self._nid.hIcon = _CALLBACK, self.icon
            self._nid.szTip = 'DeskPet · 右键打开菜单'
            self._add_icon()
            self.hotkey_registered = bool(_user32.RegisterHotKey(self.hwnd, _HOTKEY,
                                                                  0x0001 | 0x0002 | 0x4000, ord('H')))
            if not self.hotkey_registered:
                log.info('Ctrl+Alt+H 已被占用，仍可通过托盘隐藏和恢复')
        except Exception:
            self.close()
            raise

    def _add_icon(self):
        if not _shell32.Shell_NotifyIconW(0, ctypes.byref(self._nid)):
            code = ctypes.get_last_error() & 0xffffffff
            raise OSError(f'无法添加 Windows 托盘图标（0x{code:08X}）')
        self._registered = True
        self._nid.uVersion = 4
        if not _shell32.Shell_NotifyIconW(4, ctypes.byref(self._nid)):
            _shell32.Shell_NotifyIconW(2, ctypes.byref(self._nid))
            self._registered = False
            raise OSError('无法启用托盘键盘交互')

    @property
    def available(self):
        """图标或全局快捷键至少有一个可用，才允许隐藏宠物。"""
        return self._registered or self.hotkey_registered

    def _wnd_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == _CALLBACK:
                event = lparam & 0xffff
                if event in (0x400, 0x401):  # NIN_SELECT / NIN_KEYSELECT
                    self._actions.append('toggle_visibility')
                elif event == 0x007b:  # WM_CONTEXTMENU，含键盘右键菜单。
                    self._popup_menu()
                return 0
            if message == 0x0312 and wparam == _HOTKEY:
                self._actions.append('toggle_visibility')
                return 0
            if message == self._taskbar_created and self._nid is not None:
                self._registered = False
                self._next_retry = time.monotonic() + 2.0
                self._add_icon()
                return 0
            if message == 0x0010:
                self._actions.append('quit')
                return 0
        except Exception:
            log.exception('托盘事件处理失败')
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def menu_items(self):
        state = self._state
        return [('隐藏桌宠' if state.get('visible', True) else '显示桌宠', 'toggle_visibility', False),
                ('安静模式：暂停走动和提醒', 'toggle_quiet', state.get('quiet', False)),
                ('暂停学习 30 分钟', 'pause_30', state.get('paused_30', False)),
                ('今日不再提醒', 'pause_today', state.get('paused_today', False)),
                ('恢复学习', 'resume_learning', False),
                ('', None, False),
                ('回到屏幕中央', 'center', False),
                ('全屏时自动隐藏', 'toggle_fullscreen', state.get('auto_hide_fullscreen', True)),
                ('', None, False), ('保存并退出', 'quit', False)]

    def _popup_menu(self):
        menu = _user32.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        actions = {}
        try:
            for command, (label, action, checked) in enumerate(self.menu_items(), 1):
                flags = 0x0800 if action is None else (0x0008 if checked else 0)
                if not _user32.AppendMenuW(menu, flags, command, label):
                    raise ctypes.WinError(ctypes.get_last_error())
                actions[command] = action
            point = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(point))
            _user32.SetForegroundWindow(self.hwnd)
            selected = _user32.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002,
                                              point.x, point.y, 0, self.hwnd, None)
            _user32.PostMessageW(self.hwnd, 0, 0, 0)
            if actions.get(selected):
                self._actions.append(actions[selected])
        finally:
            _user32.DestroyMenu(menu)
            self._actions.append('reset_reminder')

    def set_state(self, state):
        if state == self._state:
            return
        self._state = dict(state)
        status = '提醒已暂停' if state.get('learning_paused') else '学习提醒开启'
        hotkey = ' · Ctrl+Alt+H 隐藏/恢复' if self.hotkey_registered else ''
        self._nid.szTip = f'DeskPet · {status}{hotkey}'
        _shell32.Shell_NotifyIconW(1, ctypes.byref(self._nid))

    def poll(self):
        message = wintypes.MSG()
        while self.hwnd and _user32.PeekMessageW(ctypes.byref(message), self.hwnd, 0, 0, 1):
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))
        if self.hwnd and not self._registered and time.monotonic() >= self._next_retry:
            self._next_retry = time.monotonic() + 2.0
            try:
                self._add_icon()
            except OSError:
                log.exception('托盘恢复失败，稍后重试')
        result = list(self._actions)
        self._actions.clear()
        return result

    def close(self):
        if self._registered and self._nid is not None:
            _shell32.Shell_NotifyIconW(2, ctypes.byref(self._nid))
            self._registered = False
        if self.hotkey_registered and self.hwnd:
            _user32.UnregisterHotKey(self.hwnd, _HOTKEY)
            self.hotkey_registered = False
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.icon:
            _user32.DestroyIcon(self.icon)
            self.icon = None
        if self._class_registered:
            _user32.UnregisterClassW(self._class_name, self._instance)
            self._class_registered = False
