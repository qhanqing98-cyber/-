"""第一批体验改进：运行模式、手势、互动动画和主循环数据流。"""
import ctypes
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib
import tempfile
import unittest
from unittest.mock import Mock, patch

import pygame
import character
import config
import desktop
import main
import modes
from modes import RuntimeModes
from gestures import DragGesture
from menus import ContextMenu
from pet import Pet
import pet as pet_module
import words
import window


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'settings.json')
        self.start = datetime(2026, 10, 1, 12).timestamp()
        self.model = RuntimeModes(self.path, now=self.start)

    def test_pause_30_expires_across_restart(self):
        self.model.apply_action('pause_30')
        restarted = RuntimeModes(self.path, now=self.start + 1799)
        self.assertTrue(restarted.learning_paused)
        restarted.refresh(now=self.start + 1800)
        self.assertFalse(restarted.learning_paused)

    def test_today_expires_at_local_midnight(self):
        self.model.apply_action('pause_today')
        self.model.refresh(now=datetime(2026, 10, 1, 23, 59, 59).timestamp())
        self.assertTrue(self.model.learning_paused)
        self.model.refresh(now=datetime(2026, 10, 2).timestamp())
        self.assertFalse(self.model.learning_paused)

    def test_resume_clears_all_pause_reasons(self):
        for action in ('pause_30', 'pause_today', 'toggle_quiet'):
            self.model.apply_action(action)
        self.model.apply_action('resume_learning')
        self.assertFalse(self.model.learning_paused)
        self.assertFalse(RuntimeModes(self.path, now=self.start).learning_paused)

    def test_fullscreen_auto_hide_manual_recovery_and_next_fullscreen(self):
        self.model.apply_action('toggle_fullscreen')  # 用户明确开启才自动隐藏
        self.model.refresh(fullscreen=True)
        self.assertFalse(self.model.visible)
        self.assertTrue(self.model.learning_paused)
        self.model.show()
        self.assertTrue(self.model.visible)
        self.model.refresh(fullscreen=None)
        self.assertTrue(self.model.visible)
        self.model.refresh(fullscreen=False)
        self.model.refresh(fullscreen=True)
        self.assertFalse(self.model.visible)
        self.model.apply_action('toggle_fullscreen')
        self.assertTrue(self.model.visible)

    def test_missing_recovery_keeps_visible_without_changing_preference(self):
        self.model.apply_action('toggle_fullscreen')
        self.model.hidden_by_user = True
        self.model.refresh(fullscreen=True)
        self.model.recovery_available = False
        self.assertTrue(self.model.visible)
        self.model.save()
        saved = json.loads(Path(self.path).read_text(encoding='utf-8'))
        self.assertTrue(saved['auto_hide_fullscreen'])
        self.assertNotIn('recovery_available', saved)
        restarted = RuntimeModes(self.path, now=self.start)
        self.assertTrue(restarted.visible)

    def test_failed_save_keeps_action_and_retries_only_dirty_settings(self):
        with patch.object(modes, 'write_json_atomic', side_effect=OSError('disk full')):
            self.model.apply_action('toggle_quiet')
        self.assertTrue(self.model.quiet)
        self.assertTrue(self.model.last_error)
        with patch.object(modes, 'write_json_atomic', wraps=modes.write_json_atomic) as write:
            self.assertTrue(self.model.save())
            self.assertTrue(self.model.save())
            self.assertEqual(write.call_count, 1)
        self.assertEqual(self.model.last_error, '')

    def test_corrupt_settings_are_backed_up(self):
        Path(self.path).write_text('{broken', encoding='utf-8')
        loaded = RuntimeModes(self.path, now=self.start)
        self.assertTrue(loaded.visible)
        self.assertFalse(loaded.auto_hide_fullscreen)
        self.assertEqual(len(list(Path(self.temp.name).glob('*.corrupt.bak'))), 1)
        self.assertTrue(loaded.save())

    def test_default_fullscreen_stays_visible_and_old_explicit_setting_loads(self):
        self.model.refresh(fullscreen=True)
        self.assertTrue(self.model.visible)
        self.assertFalse(self.model.auto_hide_fullscreen)
        self.assertTrue(self.model.learning_paused)
        self.assertEqual(self.model.status_text(), '全屏暂停')
        self.model.refresh(fullscreen=False)
        self.assertFalse(self.model.learning_paused)
        self.model.apply_action('toggle_fullscreen')
        loaded = RuntimeModes(self.path, now=self.start)
        loaded.refresh(fullscreen=True)
        self.assertFalse(loaded.visible)


class InteractionTests(unittest.TestCase):
    def setUp(self):
        with patch.object(Pet, '_load'):
            self.pet = Pet()
        self.area = patch.object(pet_module, 'nearest_work_area', return_value=(0, 0, 1920, 1080))
        self.area.start()
        self.addCleanup(self.area.stop)
        self.pet.x, self.pet.y = 700, 650
        self.gesture = DragGesture()

    def test_press_and_small_jitter_only_award_on_release(self):
        self.gesture.press(self.pet, 710, 640)
        self.assertEqual(self.pet.mood, 80)
        self.gesture.move(self.pet, 713, 643)
        self.assertFalse(self.pet.is_dragging)
        self.assertEqual((self.pet.x, self.pet.y), (700, 650))
        self.assertTrue(self.gesture.release(self.pet, 713, 643))
        self.assertEqual(self.pet.mood, 80 + config.CLICK_MOOD_BOOST)
        self.assertEqual(self.pet.behavior, config.B_HAPPY)
        self.assertFalse(self.gesture.release(self.pet, 713, 643))

    def test_drag_threshold_offset_and_release_do_not_award_click(self):
        self.gesture.press(self.pet, 710, 640)
        self.gesture.move(self.pet, 718, 640)
        self.assertTrue(self.pet.is_dragging)
        self.assertEqual(self.pet.behavior, config.B_LIFT)
        self.assertEqual((self.pet.x, self.pet.y), (708, 650))
        self.gesture.move(self.pet, 1000, 800)
        self.assertEqual((self.pet.x, self.pet.y), (990, 810))
        self.assertFalse(self.gesture.release(self.pet, 1000, 800))
        self.assertFalse(self.pet.is_dragging)
        self.assertEqual(self.pet.behavior, config.B_IDLE)
        self.assertEqual(self.pet.mood, 80)

    def test_large_release_without_motion_event_is_drag(self):
        self.gesture.press(self.pet, 700, 650)
        self.assertFalse(self.gesture.release(self.pet, 760, 660))
        self.assertEqual(self.pet.mood, 80)
        self.assertEqual((self.pet.x, self.pet.y), (760, 660))

    def test_cancel_lift_clamps_and_never_clicks(self):
        self.gesture.press(self.pet, 700, 650)
        self.gesture.move(self.pet, -10000, 10000)
        self.assertEqual(self.pet.x, config.PET_MARGIN_X)
        self.assertEqual(self.pet.y, 1080 - config.PET_MARGIN_BOTTOM)
        self.gesture.cancel(self.pet)
        self.assertFalse(self.pet.is_dragging)
        self.assertFalse(self.gesture.pending)
        self.assertEqual(self.pet.mood, 80)

    def test_quiet_stops_walk_but_pet_and_happy_finish(self):
        self.pet.behavior = config.B_WALK
        self.pet.settle()
        origin = self.pet.x, self.pet.y
        for _ in range(100):
            self.pet.update(frozen=True, dt=1 / 30)
        self.assertEqual((self.pet.x, self.pet.y), origin)
        self.assertEqual(self.pet.behavior, config.B_IDLE)
        for action, name in ((self.pet.on_pet, config.B_PETTING), (self.pet.on_click, config.B_HAPPY)):
            action()
            self.assertEqual(self.pet.behavior, name)
            for _ in range(40):
                self.pet.update(frozen=True, dt=1 / 30)
            self.assertTrue(self.pet.animation_finished)
            self.assertEqual(self.pet.behavior, config.B_IDLE)

    def test_recenter_uses_monitor_near_cursor(self):
        self.area.stop()
        with patch.object(desktop, 'work_areas', return_value=[(-1920, 0, 0, 1080), (0, 0, 1920, 1080)]):
            self.pet.recenter(-1400, 600)
        self.assertEqual((self.pet.x, self.pet.y), (-960, 540))


class ModeSyncTests(unittest.TestCase):
    def test_pause_resume_resets_timer_without_advancing_words(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Pet, '_load'):
            model = RuntimeModes(str(Path(folder) / 'settings.json'))
            pet = Pet()
            pet.word_timer, pet.word_bubble_active = pet.word_interval - 1, True
            menu, canvas = ContextMenu(), Mock()
            previous = model.snapshot()
            model.apply_action('pause_30')
            paused = main._sync_modes(model, pet, DragGesture(), menu, 1, canvas, previous)
            self.assertFalse(pet.word_bubble_active)
            self.assertEqual(pet.word_timer, 0)
            model.apply_action('resume_learning')
            main._sync_modes(model, pet, DragGesture(), menu, 1, canvas, paused)
            self.assertEqual(pet.word_timer, 0)
            self.assertFalse(pet.word_bubble_active)
            self.assertFalse(model.learning_paused)

    def test_hide_cancels_drag_and_show_invalidates_pixels(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Pet, '_load'), patch.object(main, 'set_window_visible') as visible:
            model = RuntimeModes(str(Path(folder) / 'settings.json'))
            pet, gesture, menu, canvas = Pet(), DragGesture(), ContextMenu(), Mock()
            previous = model.snapshot()
            gesture.press(pet, pet.x, pet.y)
            pet.begin_lift()
            menu.active = True
            model.apply_action('toggle_visibility')
            hidden = main._sync_modes(model, pet, gesture, menu, 1, canvas, previous)
            self.assertFalse(pet.is_dragging)
            self.assertFalse(menu.active)
            visible.assert_called_with(1, False)
            model.show()
            main._sync_modes(model, pet, gesture, menu, 1, canvas, hidden)
            visible.assert_called_with(1, True)
            canvas.invalidate.assert_called_once()

    def test_hide_without_recovery_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Pet, '_load'):
            model = RuntimeModes(str(Path(folder) / 'settings.json'))
            pet = Pet()
            main._dispatch_action('toggle_visibility', pet, Mock(), model, DragGesture(), False)
            self.assertTrue(model.visible)
            self.assertTrue(pet.feedback_items)


class FullscreenTests(unittest.TestCase):
    def test_fullscreen_differs_from_maximized_work_area(self):
        monitor = (0, 0, 1920, 1080)
        self.assertTrue(desktop.covers_monitor(monitor, monitor))
        self.assertFalse(desktop.covers_monitor((0, 0, 1920, 1040), monitor))
        self.assertTrue(desktop.covers_monitor((-1920, 0, 0, 1080), (-1920, 0, 0, 1080)))

    def test_own_foreground_preserves_previous_fullscreen_result(self):
        with patch.object(desktop._user32, 'GetForegroundWindow', return_value=123):
            self.assertIsNone(desktop.foreground_is_fullscreen((123,)))

    def test_detector_reads_actual_window_and_monitor_rectangles(self):
        pygame.display.init()
        try:
            pygame.display.set_mode((64, 64), pygame.NOFRAME | pygame.HIDDEN)
            hwnd = window._get_hwnd()
            user = desktop._user32
            monitor = user.MonitorFromWindow(hwnd, 2)
            info = desktop._MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            self.assertTrue(user.GetMonitorInfoW(monitor, ctypes.byref(info)))
            rect = info.rcMonitor
            self.assertTrue(user.SetWindowPos(hwnd, None, rect.left, rect.top,
                                             rect.right - rect.left, rect.bottom - rect.top, 0x14))
            window.set_window_visible(hwnd, True)
            with patch.object(user, 'GetForegroundWindow', return_value=hwnd):
                self.assertTrue(desktop.foreground_is_fullscreen())
                self.assertTrue(user.SetWindowPos(hwnd, None, rect.left, rect.top,
                                                 rect.right - rect.left, rect.bottom - rect.top - 40, 0x14))
                self.assertFalse(desktop.foreground_is_fullscreen())
                window.set_window_visible(hwnd, False)
                self.assertFalse(desktop.foreground_is_fullscreen())
        finally:
            pygame.display.quit()


class AnimationTests(unittest.TestCase):
    def test_real_character_interactions_are_distinct_and_time_based(self):
        self.assertTrue(character.load_gifs())
        sequences = []
        for name, duration in ((config.B_HAPPY, 1), (config.B_PETTING, 1.2), (config.B_LIFT, 1.2)):
            frames = character._sprite_cache[name]
            sequences.append(pygame.image.tobytes(frames[0], 'RGBA'))
            self.assertEqual(len(frames), len(character._flipped_cache[name]))
            self.assertAlmostEqual(character._frame_end_times[name][-1], duration)
            signatures = {hashlib.sha256(pygame.image.tobytes(frame, 'RGBA')).hexdigest() for frame in frames}
            self.assertGreater(len(signatures), 5, f'{name} 应有连续动作变化')
            self.assertEqual(character.animation_frame_index(name, 0.5), character.animation_frame_index(name, duration + 0.5))
            self.assertGreater(frames[0].get_bounding_rect().width, 0)
        self.assertEqual(len(set(sequences)), 3)

    def test_custom_named_animation_is_preserved(self):
        custom = pygame.Surface((40, 40), pygame.SRCALPHA)
        with patch.dict(character._sprite_cache, {'idle': [custom], 'happy': [custom]}, clear=True), patch.dict(character._flipped_cache, clear=True), patch.dict(character._frame_end_times, clear=True):
            character._build_interaction_animations()
            self.assertIs(character._sprite_cache['happy'][0], custom)


if __name__ == '__main__':
    unittest.main()
