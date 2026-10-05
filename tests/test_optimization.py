"""缓存上限、像素一致性、重复绘制、提醒时间及连续跨屏。"""
from collections import OrderedDict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pygame
import character
import config
import desktop
from gestures import DragGesture
from menus import ContextMenu
from modes import RuntimeModes
from pet import Pet
from timing import ReminderTimer
import window


class CacheTests(unittest.TestCase):
    def test_loaded_assets_and_all_interactions_stay_below_pixel_budget(self):
        self.assertTrue(character.load_gifs())
        self.assertLess(character.animation_memory_bytes(), 52 * 1024 * 1024)
        for name, frames in character._sprite_cache.items():
            for index in range(len(frames)):
                frame = frames[index]
                flipped = character._flipped_cache[name][index]
                self.assertEqual(pygame.image.tobytes(flipped, 'RGBA'),
                                 pygame.image.tobytes(pygame.transform.flip(frame, True, False), 'RGBA'))
                self.assertLessEqual(character._derived_bytes, character._DERIVED_LIMIT)
        self.assertLess(character.animation_memory_bytes(), 52 * 1024 * 1024)

    def test_eviction_regenerates_same_pixels_and_retains_list_semantics(self):
        calls = []
        def frame(index):
            calls.append(index)
            result = pygame.Surface((100, 100), pygame.SRCALPHA)
            result.fill((index * 30, 80, 100, 255))
            return result
        with patch.object(character, '_derived_frames', OrderedDict()), patch.object(character, '_derived_bytes', 0), patch.object(character, '_DERIVED_LIMIT', 80000):
            sequence = character._LazyFrames(4, 'test', frame)
            first = pygame.image.tobytes(sequence[0], 'RGBA')
            self.assertIs(sequence[0], sequence[0])
            sequence[1], sequence[2]
            self.assertEqual(first, pygame.image.tobytes(sequence[0], 'RGBA'))
            self.assertEqual(calls.count(0), 2)
            self.assertEqual(len(sequence[:2]), 2)
            self.assertEqual(sequence[-1].get_at((0, 0)).r, 90)
            with self.assertRaises(IndexError):
                sequence[4]
            self.assertLessEqual(character._derived_bytes, 80000)


class ReminderTests(unittest.TestCase):
    def setUp(self):
        with patch.object(Pet, '_load'):
            self.pet = Pet()
        self.pet.word_interval = 10
        self.timer = ReminderTimer(now=0)

    def test_real_seconds_survive_subsecond_animation_clamp(self):
        self.timer.update(self.pet, True, now=0)
        self.pet.update(dt=2)
        self.timer.update(self.pet, True, now=2)
        self.assertAlmostEqual(self.pet.animation_elapsed, 0.1)
        self.assertEqual(self.pet.word_timer, 2)
        for now in range(3, 11):
            self.timer.update(self.pet, True, now=now)
        self.assertTrue(self.pet.word_bubble_active)

    def test_resume_waits_entire_interval(self):
        self.timer.update(self.pet, True, now=0)
        self.timer.update(self.pet, True, now=4)
        self.timer.update(self.pet, True, paused=True, now=5)
        self.timer.update(self.pet, True, paused=True, now=100)
        self.timer.update(self.pet, True, now=101)
        self.assertEqual(self.pet.word_timer, 0)
        for now in range(102, 111):
            self.timer.update(self.pet, True, now=now)
        self.assertFalse(self.pet.word_bubble_active)
        self.timer.update(self.pet, True, now=111)
        self.assertTrue(self.pet.word_bubble_active)

    def test_wake_and_modal_return_hide_stale_card_without_burst(self):
        self.pet.word_bubble_active = True
        self.timer.update(self.pet, True, now=120)
        self.assertFalse(self.pet.word_bubble_active)
        self.assertEqual(self.pet.word_timer, 0)
        self.timer.update(self.pet, True, now=121)
        self.pet.reminder_reset_pending = True
        self.timer.update(self.pet, True, now=123)
        self.assertEqual(self.pet.word_timer, 0)
        self.assertFalse(self.pet.reminder_reset_pending)

    def test_open_menu_and_closed_card_each_restart_interval(self):
        self.timer.update(self.pet, True, now=0)
        self.timer.update(self.pet, True, now=4)
        self.timer.update(self.pet, True, menu_active=True, now=5)
        self.timer.update(self.pet, True, now=6)
        self.assertEqual(self.pet.word_timer, 0)
        self.pet.word_bubble_active = True
        self.timer.update(self.pet, True, now=7)
        self.pet.word_bubble_active = False
        self.timer.update(self.pet, True, now=8)
        self.assertEqual(self.pet.word_timer, 0)


class CrossScreenTests(unittest.TestCase):
    def setUp(self):
        with patch.object(Pet, '_load'):
            self.pet = Pet()
        self.areas = [(0, 0, 1920, 1080), (1920, 0, 3840, 1080)]
        context = patch.object(desktop, 'work_areas', side_effect=lambda: self.areas)
        context.start()
        self.addCleanup(context.stop)
        self.pet.x, self.pet.y = 1800, 650

    def test_drag_and_walk_cross_without_jump_or_direction_flip(self):
        gesture = DragGesture()
        gesture.press(self.pet, 1800, 650)
        for x in range(1810, 2001, 10):
            gesture.move(self.pet, x, 650)
            self.assertEqual(self.pet.x, x)
            origin = desktop.canvas_origin(x, 650, 450, 500, 225, 350)
            self.assertEqual(origin[0], x - 225)
            self.assertEqual(origin[1], 300)
        gesture.release(self.pet, 2000, 650)
        self.pet.x, self.pet.direction, self.pet.behavior = 1919, 1, config.B_WALK
        self.pet.update(dt=1 / 60)
        self.assertGreater(self.pet.x, 1920)
        self.assertEqual(self.pet.direction, 1)

    def test_stacked_screens_and_negative_coordinates(self):
        self.areas[:] = [(-1920, 0, 0, 1080), (-1920, -1080, 0, 0)]
        self.pet.x = -900
        for y in (10, 1, -1, -10):
            self.pet.y = y
            self.pet._clamp_position()
            self.assertEqual(self.pet.y, y)
            self.assertEqual(desktop.canvas_origin(-900, y, 450, 500, 225, 350)[1], y - 350)

    def test_gaps_staggering_and_disconnect_keep_character_visible(self):
        self.areas[:] = [(0, 0, 1920, 1080), (2020, 0, 3940, 1080)]
        self.pet.x = 1919
        self.pet._clamp_position()
        self.assertEqual(self.pet.x, 1820)
        self.areas[:] = [(0, 0, 1920, 1080), (1920, 500, 3840, 1580)]
        self.pet.x, self.pet.y = 1919, 200
        self.pet._clamp_position()
        self.assertEqual(self.pet.x, 1820)
        self.areas[:] = [(0, 0, 1920, 1080)]
        self.pet.x = 2500
        self.pet._clamp_position()
        self.assertEqual(self.pet.x, 1820)
        ox, oy = desktop.canvas_origin(self.pet.x, self.pet.y, 450, 500, 225, 350)
        self.assertTrue(pygame.Rect(0, 0, 1920, 1080).contains(pygame.Rect(ox, oy, 450, 500)))


class DrawingTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.addCleanup(pygame.font.quit)
        self.addCleanup(character._font_cache.clear)
        self.addCleanup(character._cached_word_bubble_layout.cache_clear)
        with patch.object(Pet, '_load'):
            self.pet = Pet()
        self.menu = ContextMenu()

    def test_scene_key_ignores_world_position_but_tracks_visible_changes(self):
        self.pet.panel_timer = 0
        def key():
            return character.scene_key(self.pet, None, '', self.menu, True, (225, 350), '学习开启')
        original = key()
        self.pet.x += 10
        self.pet.hunger -= 0.1
        self.assertEqual(key(), original)
        self.pet.panel_timer = 2
        self.assertNotEqual(key(), original)
        with_panel = key()
        self.pet.word_bubble_active = True
        self.assertNotEqual(key(), with_panel)

    def test_feed_button_visible_bounds_and_hover_invalidation(self):
        self.pet.panel_timer = 0
        self.pet.is_hovered = False
        self.assertIsNone(character.get_feed_button_rect(self.pet))
        self.pet.is_hovered = True
        for center in ((100, 140), (350, 140), (100, 390), (350, 390)):
            button = character.get_feed_button_rect(self.pet, center)
            self.assertTrue(pygame.Rect(0, 0, 450, 500).contains(button))
            surface = pygame.Surface((450, 500), pygame.SRCALPHA)
            character.draw_status(surface, self.pet, center)
            self.assertGreater(surface.get_at(button.center).a, 0)
        before = character.scene_key(self.pet, None, '', self.menu, False, (225, 350), '学习开启')
        self.pet.feed_hovered = True
        self.assertNotEqual(before, character.scene_key(self.pet, None, '', self.menu, False, (225, 350), '学习开启'))
        self.pet.word_bubble_active = True
        self.assertIsNone(character.get_feed_button_rect(self.pet))

    def test_card_hit_region_and_modes_render_inside_canvas_at_edges(self):
        word = {'word': 'performance', 'meaning': '保持当前风格，并让跨屏移动更加顺畅。'}
        self.pet.is_hovered = True
        for center in ((100, 140), (350, 140), (100, 390), (350, 390)):
            surface = pygame.Surface((450, 500), pygame.SRCALPHA)
            rect = character.get_word_bubble_rect(word, '1/100', center)
            self.assertTrue(surface.get_rect().contains(rect))
            character.draw_word_bubble(surface, word, '1/100', center)
            self.assertGreater(surface.get_at(rect.center).a, 0)
        surface = pygame.Surface((450, 500), pygame.SRCALPHA)
        character.draw_status(surface, self.pet, (100, 140), '学习开启')
        before = pygame.image.tobytes(surface, 'RGBA')
        surface.fill((0, 0, 0, 0))
        character.draw_status(surface, self.pet, (100, 140), '安静中')
        self.assertNotEqual(before, pygame.image.tobytes(surface, 'RGBA'))

    def test_position_only_present_does_not_convert_or_upload_pixels(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        pygame.display.set_mode((32, 32), pygame.NOFRAME | pygame.HIDDEN)
        hwnd = window._get_hwnd()
        window._set_window_layered(hwnd)
        canvas = window._LayeredCanvas(hwnd, 32, 32)
        self.addCleanup(canvas.close)
        surface = pygame.Surface((32, 32), pygame.SRCALPHA)
        surface.fill((100, 150, 200, 128))
        canvas.present(surface, 100, 100)
        with patch.object(pygame.image, 'tobytes', side_effect=AssertionError('不应转换像素')), patch.object(window._user32, 'UpdateLayeredWindow', wraps=window._user32.UpdateLayeredWindow) as upload:
            self.assertFalse(canvas.present(surface, 100, 100, content_changed=False))
            self.assertTrue(canvas.present(surface, 110, 100, content_changed=False))
            self.assertIsNone(upload.call_args.args[4])
        canvas.invalidate()
        self.assertTrue(canvas.present(surface, 110, 100, content_changed=False))

    def test_window_topmost_is_applied_on_setup_and_restore_without_focus(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        pygame.display.set_mode((32, 32), pygame.NOFRAME | pygame.HIDDEN)
        hwnd = window._get_hwnd()
        focused = window._user32.GetForegroundWindow()
        with patch.object(window._user32, 'SetWindowPos', wraps=window._user32.SetWindowPos) as position:
            window._set_window_layered(hwnd)
            window.set_window_visible(hwnd, True)
            self.assertEqual(position.call_count, 2)
            self.assertTrue(all(call.args[-1] & 0x10 for call in position.call_args_list))
        self.assertTrue(window._user32.GetWindowLongW(hwnd, window._GWL_EXSTYLE) & window._WS_EX_TOPMOST)
        self.assertEqual(window._user32.GetForegroundWindow(), focused)


class ModeFeedbackTests(unittest.TestCase):
    def test_pause_reason_and_remaining_minutes(self):
        with tempfile.TemporaryDirectory() as folder:
            model = RuntimeModes(str(Path(folder) / 'settings.json'), now=1000)
            model.apply_action('pause_30')
            self.assertEqual(model.status_text(), '暂停·30分钟')
            model.refresh(now=1060)
            self.assertEqual(model.status_text(), '暂停·29分钟')
            model.apply_action('toggle_quiet')
            self.assertEqual(model.status_text(), '安静中')
            model.apply_action('resume_learning')
            self.assertEqual(model.status_text(), '学习开启')


if __name__ == '__main__':
    unittest.main()
