"""Windows 透明窗口、输入查询与绘图资源管理。"""
import ctypes
from ctypes import wintypes
import numpy as np
import pygame

# ─── Windows API 常量 ────────────────────────
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080

_VK_LBUTTON = 0x01

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32


def _get_hwnd():
    return pygame.display.get_wm_info()['window']


# 显式声明 64 位指针类型，避免句柄被截断导致比较失配
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.SetWindowPos.restype = wintypes.BOOL


def ensure_topmost(hwnd):
    """设置真实窗口层级，不移动、不缩放、不抢键盘焦点。"""
    if not _user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x13):
        raise OSError('无法设置桌宠置顶')


def set_window_visible(hwnd, visible):
    # SW_SHOWNOACTIVATE：从托盘恢复时不抢走正在输入的键盘焦点。
    _user32.ShowWindow(hwnd, 4 if visible else 0)
    if visible:
        ensure_topmost(hwnd)


def _window_focused(hwnd):
    """窗口是否持有键盘焦点（键盘交互的前提）"""
    return _user32.GetForegroundWindow() == hwnd


def _set_window_layered(hwnd):
    """只设置分层/置顶/工具窗口样式。
    透明不再用品红色键（半透明会和品红混合成紫色），
    而是由 _LayeredCanvas 每帧上传每像素 alpha。"""
    current = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    style = current | _WS_EX_LAYERED | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW
    _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
    ensure_topmost(hwnd)


def _set_clickthrough(hwnd, enabled):
    current = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    if enabled:
        _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                               current | _WS_EX_TRANSPARENT)
    else:
        _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                               current & ~_WS_EX_TRANSPARENT)


def _get_cursor_screen_pos():
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _is_lbutton_pressed():
    """全局检测左键是否按下（不依赖窗口焦点）"""
    return (_user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000) != 0


# ─── 每像素 alpha 分层窗口 ──────────────────
# 色键透明只能做"要么全透明要么不透明"，半透明 UI 会和键控色混合
# 变成脏紫色。改用 UpdateLayeredWindow：把整帧场景（真 alpha）经
# GDI 位图上传为窗口像素，并顺带完成窗口移动。
_ULW_ALPHA = 0x02
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01
_DIB_RGB_COLORS = 0


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', wintypes.BYTE),
                ('BlendFlags', wintypes.BYTE),
                ('SourceConstantAlpha', wintypes.BYTE),
                ('AlphaFormat', wintypes.BYTE)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', _BITMAPINFOHEADER)]


_user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC,
    ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    wintypes.COLORREF, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
_user32.UpdateLayeredWindow.restype = wintypes.BOOL
_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HBITMAP]
_gdi32.SelectObject.restype = wintypes.HBITMAP
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]


class _LayeredCanvas:
    """把带真 alpha 的 pygame 场景每帧上传为窗口像素。

    数据流：SRCALPHA 场景面 → tobytes('BGRA') → numpy 预乘 alpha
    （AC_SRC_ALPHA 要求 RGB 已乘以 alpha/255）→ memmove 进 DIB 位图
    → UpdateLayeredWindow 上屏 + 移动窗口。"""

    def __init__(self, hwnd, w, h):
        self.hwnd = hwnd
        self.w, self.h = w, h
        self._last_raw = None
        self._last_pos = None
        self._old_bitmap = None
        self._hdc = self._hbm = None
        hdc_screen = _user32.GetDC(None)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h   # 负高度 = 自上而下行序，与 pygame 一致
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        self._bits = ctypes.c_void_p()
        self._hbm = _gdi32.CreateDIBSection(
            hdc_screen, ctypes.byref(bmi), _DIB_RGB_COLORS,
            ctypes.byref(self._bits), None, 0)
        self._hdc = _gdi32.CreateCompatibleDC(hdc_screen)
        if self._hbm and self._hdc:
            self._old_bitmap = _gdi32.SelectObject(self._hdc, self._hbm)
        _user32.ReleaseDC(None, hdc_screen)
        if not self._hbm or not self._hdc or not self._bits:
            self.close()
            raise OSError('无法创建透明窗口画布')
        self._bf = _BLENDFUNCTION(_AC_SRC_OVER, 0, 255, _AC_SRC_ALPHA)
        self._size = wintypes.SIZE(w, h)
        self._src_pt = wintypes.POINT(0, 0)

    def present(self, scene, x, y, content_changed=True):
        if not content_changed and self._last_raw is not None:
            return self.move(x, y)
        raw = pygame.image.tobytes(scene, 'BGRA')
        pos = int(x), int(y)
        if raw == self._last_raw and pos == self._last_pos:
            return False
        if raw == self._last_raw:
            return self.move(x, y)
        if raw != self._last_raw:
            arr = np.frombuffer(raw, np.uint8).reshape(self.h, self.w, 4).copy()
            alpha = arr[:, :, 3:4].astype(np.uint16)
            arr[:, :, :3] = (arr[:, :, :3].astype(np.uint16) * alpha // 255).astype(np.uint8)
            ctypes.memmove(self._bits, arr.tobytes(), self.w * self.h * 4)
        dst_pt = wintypes.POINT(int(x), int(y))
        ok = _user32.UpdateLayeredWindow(
            self.hwnd, None, ctypes.byref(dst_pt), ctypes.byref(self._size),
            self._hdc, ctypes.byref(self._src_pt), 0,
            ctypes.byref(self._bf), _ULW_ALPHA)
        if not ok:
            raise OSError('透明窗口上传失败')
        self._last_raw, self._last_pos = raw, pos
        return True

    def move(self, x, y):
        """内容不变时只移动窗口，不转换像素、不上传位图。"""
        pos = int(x), int(y)
        if pos == self._last_pos:
            return False
        point = wintypes.POINT(*pos)
        if not _user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(point), None,
                                          None, None, 0, None, 0):
            raise OSError('透明窗口移动失败')
        self._last_pos = pos
        return True

    def close(self):
        """先恢复旧位图，再删除本对象的位图和 DC；可重复调用。"""
        if self._hdc and self._old_bitmap:
            _gdi32.SelectObject(self._hdc, self._old_bitmap)
            self._old_bitmap = None
        if self._hbm:
            _gdi32.DeleteObject(self._hbm)
            self._hbm = None
        if self._hdc:
            _gdi32.DeleteDC(self._hdc)
            self._hdc = None

    def invalidate(self):
        """恢复窗口后确保下一帧重新上传。"""
        self._last_raw = self._last_pos = None


