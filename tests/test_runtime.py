"""隐藏窗口运行真实主循环；不会接触用户实际存档。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import json
import pygame
import character
import main
import pet as pet_module
import words
import ui_theme
from modes import RuntimeModes


class FakeTray:
    """主循环测试使用可控托盘；原生图标另有真实桌面集成测试。"""
    def __init__(self, sprite):
        self.hwnd = None
        self.available = True
        self.states = []
        self.closed = False

    def poll(self):
        return []

    def set_state(self, state):
        self.states.append(dict(state))

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
    def run_app(self, crash=False, autosave=False, actions=None, failed_tray=False, mouse_feed=None, escape=False):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'words_A.json').write_text(json.dumps({'words': [
                {'word': 'test', 'meaning': '测试'}, {'word': 'flow', 'meaning': '流动'}],
                'index': 0}), encoding='utf-8')
            real_set_mode = pygame.display.set_mode
            real_mutex = main.ctypes.windll.kernel32.CreateMutexW
            real_mutex.argtypes = [main.wintypes.LPCVOID, main.wintypes.BOOL, main.wintypes.LPCWSTR]
            real_mutex.restype = main.wintypes.HANDLE
            unique_name = 'DeskPet_Test_' + uuid.uuid4().hex
            frames = [0]
            created_trays = []

            class ScriptedTray(FakeTray):
                def __init__(self, sprite):
                    if failed_tray:
                        raise OSError('injected tray failure')
                    super().__init__(sprite)
                    self.poll_count = 0
                    created_trays.append(self)

                def poll(self):
                    self.poll_count += 1
                    return (actions or {}).get(self.poll_count, [])

            def events():
                frames[0] += 1
                if frames[0] == 1:
                    if mouse_feed:
                        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
                                pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                                   pos=(20, 20) if mouse_feed == 'click' else (300, 400))]
                    return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f)]
                if frames[0] == 5:
                    return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)]
                if frames[0] == 10:
                    return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE if escape else pygame.K_SPACE)]
                if frames[0] >= 15:
                    if crash:
                        raise RuntimeError('injected runtime failure')
                    return [pygame.event.Event(pygame.QUIT)]
                return []

            contexts = [patch.object(main, '_install_crash_logger'),
                        patch.object(main, 'prepare_data_directory'),
                        patch.object(main, 'RuntimeModes', side_effect=lambda: RuntimeModes(str(directory / 'settings.json'))),
                        patch.object(main, 'TrayIcon', ScriptedTray),
                        patch.object(main, 'foreground_is_fullscreen', return_value=failed_tray),
                        patch.object(main, 'AUTOSAVE_INTERVAL', 0 if autosave else 30),
                        patch.object(pet_module, 'SAVE_FILE', str(directory / 'save.json')),
                        patch.object(words, '_DIR', folder),
                        patch.object(words, 'INDEX_FILE', str(directory / 'words_index.json')),
                        patch.object(words, 'OLD_FILE', str(directory / 'words.json')),
                        patch.object(pygame.display, 'set_mode', side_effect=lambda size, flags: real_set_mode(size, flags | pygame.HIDDEN)),
                        patch.object(pygame.event, 'get', side_effect=events),
                        patch.object(main.ctypes.windll.kernel32, 'CreateMutexW', side_effect=lambda a, b, c: real_mutex(a, b, unique_name)),
                        patch.object(pet_module.Pet, 'save', autospec=True, wraps=None)]
            # 记录保存调用次数，同时执行真实的存档写入。
            real_save = pet_module.Pet.save
            contexts[-1] = patch.object(pet_module.Pet, 'save', autospec=True, side_effect=real_save)
            started = []
            try:
                for context in contexts:
                    started.append(context)
                    context.start()
                if crash:
                    with self.assertRaisesRegex(RuntimeError, 'injected'):
                        main.main()
                else:
                    main.main()
                self.assertFalse(pygame.get_init())
                self.assertTrue((directory / 'save.json').exists())
                saved = json.loads((directory / 'save.json').read_text(encoding='utf-8'))
                if mouse_feed == 'cancel':
                    self.assertLess(saved['hunger'], 81)
                else:
                    self.assertGreater(saved['hunger'], 94)
                self.assertGreater(saved['mood'], 87)
                calls = pet_module.Pet.save.call_count
                self.assertGreater(calls, 1) if autosave else self.assertEqual(calls, 1)
                self.assertIn('idle', character._frame_end_times)
                settings = json.loads((directory / 'settings.json').read_text(encoding='utf-8'))
                self.assertFalse(settings['auto_hide_fullscreen'])
                if escape:
                    self.assertEqual(frames[0], 15)
                for icon in created_trays:
                    self.assertTrue(icon.closed)
                return created_trays, settings
            finally:
                for context in reversed(started):
                    context.stop()
                character._font_cache.clear()
                character._cached_word_bubble_layout.cache_clear()

    def test_normal_exit_and_actual_gifs(self):
        self.run_app()

    def test_escape_does_not_exit(self):
        self.run_app(escape=True)

    def test_quick_feed_without_focus_and_release_outside_cancels(self):
        with patch.object(character, 'get_feed_button_rect', return_value=pygame.Rect(10, 10, 148, 22)), \
                patch.object(main, '_get_cursor_screen_pos', return_value=(-999, -999)), \
                patch.object(main, '_window_focused', return_value=False), \
                patch.object(main._user32, 'SetForegroundWindow') as focus:
            self.run_app(mouse_feed='click')
            self.run_app(mouse_feed='cancel')
            focus.assert_not_called()

    def test_exception_still_saves_and_releases_window(self):
        self.run_app(crash=True)

    def test_periodic_autosave(self):
        self.run_app(autosave=True)

    def test_tray_actions_flow_through_main_and_save_on_quit(self):
        icons, settings = self.run_app(actions={
            2: ['pause_30'], 3: ['resume_learning'], 4: ['toggle_quiet'],
            5: ['toggle_visibility'], 6: ['center'], 7: ['resume_learning'],
            8: ['pause_today'], 9: ['resume_learning'], 15: ['quit']})
        states = icons[0].states
        self.assertTrue(any(state['paused_30'] for state in states))
        self.assertTrue(any(state['paused_today'] for state in states))
        self.assertTrue(any(state['quiet'] and not state['visible'] for state in states))
        self.assertTrue(any(state['quiet'] and state['visible'] for state in states))
        self.assertTrue(states[-1]['visible'])
        self.assertFalse(states[-1]['learning_paused'])
        self.assertFalse(settings['quiet'])
        self.assertEqual(settings['pause_until'], 0)
        self.assertEqual(settings['muted_date'], '')

    def test_tray_failure_keeps_visible_and_preserves_fullscreen_preference(self):
        with patch.object(main, 'set_window_visible') as visibility:
            self.run_app(failed_tray=True)
        visibility.assert_not_called()

    def test_card_layout_cache_matches_hit_region_and_stays_bounded(self):
        pygame.font.init()
        try:
            character._font_cache.clear()
            character._cached_word_bubble_layout.cache_clear()
            for i in range(40):
                word = {'word': f'word{i}', 'meaning': '这是用于验证卡片布局和点击区域的一段释义。'}
                rect = character.get_word_bubble_rect(word, f'{i + 1}/40')
                scene = pygame.Surface((450, 500), pygame.SRCALPHA)
                character.draw_word_bubble(scene, word, f'{i + 1}/40')
                self.assertTrue(scene.get_rect().contains(rect))
                self.assertGreater(scene.get_at(rect.center).a, 0)
            self.assertLessEqual(character._cached_word_bubble_layout.cache_info().currsize, 32)
            for i in range(150):
                ui_theme.translucent_rounded(scene, (50, 70, 90, 150), (0, 0, 20 + i, 20), 4)
            self.assertLessEqual(ui_theme._translucent_panel.cache_info().currsize, 128)
        finally:
            character._font_cache.clear()
            character._cached_word_bubble_layout.cache_clear()
            pygame.font.quit()
