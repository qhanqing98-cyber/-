"""有真实 Windows 任务栏时验证原生托盘；无任务栏时明确跳过。"""
import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import patch

import pygame
import tray

tray._user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
tray._user32.FindWindowW.restype = wintypes.HWND


@unittest.skipUnless(tray._user32.FindWindowW('Shell_TrayWnd', None), '需要真实 Windows 任务栏')
class NativeTrayTests(unittest.TestCase):
    def test_native_icon_callbacks_hotkey_recovery_and_cleanup(self):
        sprite = pygame.Surface((32, 32), pygame.SRCALPHA)
        sprite.fill((119, 142, 177, 255))
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        get_resources = tray._user32.GetGuiResources
        get_resources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        # 先预热系统图标缓存，再检查重复创建释放后的 GDI/USER 资源。
        warmup = tray.TrayIcon(sprite)
        warmup.close()
        baseline = [get_resources(kernel.GetCurrentProcess(), kind) for kind in (0, 1)]
        for _ in range(3):
            icon = tray.TrayIcon(sprite)
            try:
                self.assertTrue(icon._registered)
                self.assertTrue(icon.available)
                icon.set_state({'visible': False, 'quiet': True, 'learning_paused': True})
                self.assertEqual(icon.menu_items()[0][0], '显示桌宠')
                self.assertTrue(icon.menu_items()[1][2])
                for event in (0x400, 0x401):
                    self.assertTrue(tray._user32.PostMessageW(icon.hwnd, tray._CALLBACK, 0, (1 << 16) | event))
                    self.assertEqual(icon.poll(), ['toggle_visibility'])
                if icon.hotkey_registered:
                    self.assertTrue(tray._user32.PostMessageW(icon.hwnd, 0x0312, tray._HOTKEY, 0))
                    self.assertEqual(icon.poll(), ['toggle_visibility'])
                # Explorer 重建托盘时图标已经丢失；不重启或关闭用户的 Explorer。
                self.assertTrue(tray._shell32.Shell_NotifyIconW(2, ctypes.byref(icon._nid)))
                self.assertTrue(tray._user32.PostMessageW(icon.hwnd, icon._taskbar_created, 0, 0))
                icon.poll()
                self.assertTrue(icon._registered)
                self.assertTrue(tray._shell32.Shell_NotifyIconW(1, ctypes.byref(icon._nid)))
                # 使用真实菜单创建/释放，仅拦截阻塞选择，验证菜单动作进入队列。
                with patch.object(tray._user32, 'TrackPopupMenu', return_value=7), patch.object(tray._user32, 'SetForegroundWindow'):
                    icon._popup_menu()
                self.assertEqual(icon.poll(), ['center', 'reset_reminder'])
                self.assertTrue(tray._user32.PostMessageW(icon.hwnd, 0x0010, 0, 0))
                self.assertEqual(icon.poll(), ['quit'])
            finally:
                icon.close()
                icon.close()
            self.assertIsNone(icon.hwnd)
            self.assertIsNone(icon.icon)
            self.assertFalse(icon.available)
        after = [get_resources(kernel.GetCurrentProcess(), kind) for kind in (0, 1)]
        self.assertEqual(after, baseline)


if __name__ == '__main__':
    unittest.main()
