"""显示器工作区域：排除任务栏，支持负坐标和显示器断开。"""
import ctypes
from ctypes import wintypes
import time

_user32 = ctypes.windll.user32
_areas = []
_last_refresh = -10.0


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


_MonitorCallback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE,
                                      wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
_user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                       _MonitorCallback, wintypes.LPARAM]
_user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HANDLE


def work_areas():
    global _areas, _last_refresh
    now = time.monotonic()
    if now - _last_refresh >= 1:
        areas = []

        @_MonitorCallback
        def collect(monitor, dc, rect, data):
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcWork
                areas.append((r.left, r.top, r.right, r.bottom))
            return True

        _user32.EnumDisplayMonitors(None, None, collect, 0)
        if areas:
            _areas = areas
        _last_refresh = now
    return _areas or [(0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))]


def nearest_work_area(x, y, areas=None):
    areas = work_areas() if areas is None else areas
    def distance(area):
        left, top, right, bottom = area
        return (x - max(left, min(right, x))) ** 2 + (y - max(top, min(bottom, y))) ** 2
    return min(areas, key=distance)


def covers_monitor(rect, monitor, tolerance=2):
    left, top, right, bottom = rect
    ml, mt, mr, mb = monitor
    return (left <= ml + tolerance and top <= mt + tolerance
            and right >= mr - tolerance and bottom >= mb - tolerance)


def movement_bounds(x, y, area, margin_x, margin_top, margin_bottom, areas=None):
    """外侧留角色边距；相邻屏幕共享的边缘允许连续通过。"""
    areas = work_areas() if areas is None else areas
    left, top, right, bottom = area
    min_x, max_x = left + margin_x, right - margin_x
    min_y, max_y = top + margin_top, bottom - margin_bottom
    for other in areas:
        if other == area:
            continue
        ol, ot, ore, ob = other
        if ot + margin_top <= y <= ob - margin_bottom:
            if abs(ore - left) <= 2:
                min_x = left
            if abs(ol - right) <= 2:
                max_x = right
        if ol + margin_x <= x <= ore - margin_x:
            if abs(ob - top) <= 2:
                min_y = top
            if abs(ot - bottom) <= 2:
                max_y = bottom
    return min_x, min_y, max(min_x, max_x), max(min_y, max_y)


def canvas_origin(x, y, width, height, anchor_x, anchor_y):
    """外侧画布留在屏幕内；共享边缘允许画布横跨，避免角色被切掉。"""
    left, top, right, bottom = nearest_work_area(x, y)
    for ol, ot, ore, ob in work_areas():
        overlap_top, overlap_bottom = max(top, ot), min(bottom, ob)
        overlap_left, overlap_right = max(left, ol), min(right, ore)
        if overlap_bottom - overlap_top >= height and overlap_top <= y <= overlap_bottom:
            if abs(ore - left) <= 2 and x - left < anchor_x:
                left, top, bottom = ol, overlap_top, overlap_bottom
            elif abs(ol - right) <= 2 and right - x < width - anchor_x:
                right, top, bottom = ore, overlap_top, overlap_bottom
        if overlap_right - overlap_left >= width and overlap_left <= x <= overlap_right:
            if abs(ob - top) <= 2 and y - top < anchor_y:
                top, left, right = ot, overlap_left, overlap_right
            elif abs(ot - bottom) <= 2 and bottom - y < height - anchor_y:
                bottom, left, right = ob, overlap_left, overlap_right
    ox = max(left, min(max(left, right - width), round(x) - anchor_x))
    oy = max(top, min(max(top, bottom - height), round(y) - anchor_y))
    return int(ox), int(oy)


def foreground_is_fullscreen(ignored_hwnds=()):
    """忽略自己的窗口时返回 None，避免打开托盘菜单打断全屏判断。"""
    hwnd = _user32.GetForegroundWindow()
    if hwnd in ignored_hwnds:
        return None
    if not hwnd or not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
        return False
    name = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, name, len(name))
    if name.value in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
        return False
    rect = wintypes.RECT()
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    monitor = _user32.MonitorFromWindow(hwnd, 2)
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)) or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    r = info.rcMonitor
    return covers_monitor((rect.left, rect.top, rect.right, rect.bottom),
                          (r.left, r.top, r.right, r.bottom))
