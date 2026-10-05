"""验证失败恢复、进度分离、帧率独立性与真实 Windows 资源释放。"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pygame
import character
import config
import desktop
import pet as pet_module
from pet import Pet
import storage
import words
import window


class WordStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        contexts = [patch.object(words, '_DIR', self.temp.name),
                    patch.object(words, 'INDEX_FILE', str(self.directory / 'words_index.json')),
                    patch.object(words, 'OLD_FILE', str(self.directory / 'words.json')),
                    patch.object(words, 'get_resource_path', return_value=self.temp.name)]
        for context in contexts:
            context.start()
            self.addCleanup(context.stop)

    def book(self, name='A', index=0):
        target = Path(words._book_path(name))
        target.write_text(json.dumps({'words': [{'word': 'one', 'meaning': '一'},
                                                {'word': 'two', 'meaning': '二'}],
                                     'index': index}), encoding='utf-8')
        return target

    def test_advance_only_writes_progress_and_survives_restart(self):
        target = self.book()
        manager = words.WordList()
        old, old_index = target.read_bytes(), Path(words.INDEX_FILE).read_bytes()
        with patch.object(words, '_write_json_atomic', wraps=storage.write_json_atomic) as writer:
            self.assertTrue(manager.advance())
            self.assertEqual(writer.call_count, 1)
            self.assertEqual(writer.call_args.args[0], words._progress_path('A'))
        self.assertEqual(target.read_bytes(), old)
        self.assertEqual(Path(words.INDEX_FILE).read_bytes(), old_index)
        self.assertEqual(words.WordList().index, 1)

    def test_failed_progress_retries_without_rewriting_book(self):
        target = self.book()
        manager = words.WordList()
        with patch.object(words, '_write_json_atomic', side_effect=OSError('disk full')):
            self.assertFalse(manager.advance())
            self.assertIn('A', manager._progress_dirty)
        old = target.read_bytes()
        self.assertTrue(manager.save())
        self.assertEqual(target.read_bytes(), old)
        self.assertEqual(words.WordList().index, 1)

    def test_corrupt_book_is_backed_up_and_not_overwritten(self):
        target = self.book()
        target.write_text('{broken', encoding='utf-8')
        manager = words.WordList()
        manager.words = [{'word': 'replacement', 'meaning': ''}]
        self.assertFalse(manager.save())
        self.assertEqual(target.read_text(encoding='utf-8'), '{broken')
        self.assertTrue(list(self.directory.glob('*.corrupt.bak')))

    def test_invalid_types_and_indices_are_handled(self):
        self.book(index=-999)
        manager = words.WordList()
        self.assertEqual(manager.index, 0)
        manager.index = 999
        self.assertEqual(manager.index, 1)
        for content in ('[{"word":123}]', '[{"word":"one","meaning":null}]', 'null'):
            self.assertFalse(manager._parse_json(content)[0])
        self.assertFalse(words._valid_name('../escape'))

    def test_csv_quotes_multiline_header_and_duplicates(self):
        manager = words.WordList()
        parsed = manager._parse_csv('word,meaning\nhello,"你好,朋友"\nhello,"你好,朋友"\nworld,"第一行\n第二行"\n')
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['meaning'], '你好,朋友')
        self.assertEqual(parsed[1]['meaning'], '第一行\n第二行')

    def test_same_name_import_preserves_original(self):
        target = self.book()
        manager = words.WordList()
        incoming = self.directory / 'incoming.txt'
        incoming.write_text('new|新', encoding='utf-8')
        original = target.read_bytes()
        self.assertTrue(manager.import_file(str(incoming), 'A')[0])
        self.assertEqual(manager.active_book, 'A (2)')
        self.assertEqual(target.read_bytes(), original)

    def test_failed_import_keeps_current_book(self):
        self.book()
        manager = words.WordList()
        incoming = self.directory / 'incoming.txt'
        incoming.write_text('new|新', encoding='utf-8')
        with patch.object(words, '_write_json_atomic', side_effect=OSError('read only')):
            self.assertFalse(manager.import_file(str(incoming), 'B')[0])
        self.assertEqual(manager.active_book, 'A')
        self.assertNotIn('B', manager.books)

    def test_legacy_migration_preserves_active_and_backup(self):
        Path(words.OLD_FILE).write_text(json.dumps({'active_book': 'B', 'books': {
            'A': {'words': [{'word': 'a'}], 'index': 0},
            'B': {'words': [{'word': 'b'}, {'word': 'c'}], 'index': 1}}}), encoding='utf-8')
        manager = words.WordList()
        self.assertEqual(manager.active_book, 'B')
        self.assertEqual(manager.index, 1)
        self.assertTrue(Path(words.OLD_FILE + '.migrated.bak').exists())

    def test_corrupt_index_recovers_all_books(self):
        self.book('A')
        self.book('B')
        Path(words.INDEX_FILE).write_text('{broken', encoding='utf-8')
        manager = words.WordList()
        self.assertEqual(manager.list_books(), ['A', 'B'])
        self.assertTrue(list(self.directory.glob('words_index.json.*.corrupt.bak')))


class PetSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / 'save.json'
        self.addCleanup(self.temp.cleanup)
        context = patch.object(pet_module, 'SAVE_FILE', str(self.target))
        context.start()
        self.addCleanup(context.stop)

    def test_atomic_failure_keeps_original(self):
        pet = Pet()
        self.assertTrue(pet.save())
        old = self.target.read_bytes()
        pet.hunger = 5
        with patch.object(storage.os, 'replace', side_effect=OSError('disk full')):
            self.assertFalse(pet.save())
        self.assertEqual(self.target.read_bytes(), old)
        self.assertFalse(list(self.target.parent.glob('*.tmp')))

    def test_corrupt_save_creates_backup(self):
        self.target.write_text('{broken', encoding='utf-8')
        pet = Pet()
        self.assertTrue(list(self.target.parent.glob('*.corrupt.bak')))
        self.assertTrue(pet.save())

    def test_backup_failure_blocks_overwrite(self):
        self.target.write_text('{broken', encoding='utf-8')
        with patch.object(pet_module, 'backup_corrupt', side_effect=OSError('permission')):
            pet = Pet()
        self.assertFalse(pet.save())
        self.assertEqual(self.target.read_text(encoding='utf-8'), '{broken')

    def test_invalid_values_default_or_clamp(self):
        self.target.write_text(json.dumps({'hunger': 'wrong', 'mood': -20,
                                          'energy': 200, 'x': float('nan'),
                                          'word_interval': 0}), encoding='utf-8')
        pet = Pet()
        self.assertEqual((pet.hunger, pet.mood, pet.energy), (80, 0, 100))
        self.assertEqual(pet.word_interval, 10)
        self.assertTrue(pet.save())


class TimingTests(unittest.TestCase):
    def test_different_fps_produce_same_state_and_particles(self):
        results = []
        with patch.object(Pet, '_load'), patch.object(pet_module, 'nearest_work_area', return_value=(0, 0, 4000, 2000)):
            for fps in (30, 60, 120):
                pet = Pet()
                pet.x, pet.y = 600, 700
                pet.behavior = config.B_WALK
                pet.feedback_items = [{'life': 120, 'max_life': 120, 'x': 0, 'y': 0,
                                       'vx': 1, 'vy': 2, 'alpha': 1}]
                for _ in range(fps):
                    pet.update(dt=1 / fps)
                results.append((pet.x, pet.hunger, pet.energy, pet.animation_elapsed,
                                pet.feedback_items[0]['x'], pet.feedback_items[0]['alpha']))
        for candidate in results[1:]:
            for actual, expected in zip(candidate, results[0]):
                self.assertAlmostEqual(actual, expected)

    def test_gif_frame_durations_and_draw_is_read_only(self):
        frames = [pygame.Surface((10, 10), pygame.SRCALPHA) for _ in range(3)]
        with patch.dict(character._sprite_cache, {'idle': frames}, clear=True), patch.dict(character._frame_end_times, {'idle': [0.05, 0.20, 0.30]}, clear=True), patch.object(Pet, '_load'):
            pet = Pet()
            pet.animation_elapsed = 0.12
            self.assertEqual(character.animation_frame_index('idle', 0.12), 1)
            self.assertEqual(character.animation_frame_index('idle', 0.31), 0)
            for _ in range(10):
                character.draw_pet(pygame.Surface((450, 500)), pet)
            self.assertEqual(pet.animation_elapsed, 0.12)

    def test_dialog_pause_does_not_jump(self):
        with patch.object(Pet, '_load'):
            pet = Pet()
            pet.on_click()
            pet.update(dt=300)
            self.assertLessEqual(pet.animation_elapsed, 0.1)
            self.assertEqual(pet.behavior, config.B_HAPPY)


class DesktopTests(unittest.TestCase):
    def test_negative_monitor_and_disconnection(self):
        with patch.object(Pet, '_load'), patch.object(pet_module, 'nearest_work_area', side_effect=lambda x, y: desktop.nearest_work_area(x, y, [(-1920, 0, 0, 1040)])):
            pet = Pet()
            pet.x, pet.y = -500, 800
            pet._clamp_position()
            self.assertEqual((pet.x, pet.y), (-500, 800))
        with patch.object(pet_module, 'nearest_work_area', return_value=(0, 0, 1920, 1040)):
            pet._clamp_position()
            self.assertEqual(pet.x, config.PET_MARGIN_X)

    def test_exe_data_directory_and_portable_flag(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config.sys, 'frozen', True, create=True), patch.object(config.sys, 'executable', str(Path(folder) / 'DeskPet.exe')), patch.dict(os.environ, {'LOCALAPPDATA': folder, 'DESKPET_DATA_DIR': ''}):
            self.assertEqual(config.get_data_path(), str(Path(folder) / 'DeskPet'))
            (Path(folder) / 'portable.flag').touch()
            self.assertEqual(config.get_data_path(), folder)

    def test_migration_keeps_existing_save_and_copies_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'exe', Path(folder) / 'data'
            source.mkdir()
            target.mkdir()
            (source / 'save.json').write_text('old')
            (target / 'save.json').write_text('new')
            (source / 'words_A.json').write_text('{}')
            (source / 'progress').mkdir()
            (source / 'progress' / 'words_A.json').write_text('{"index":2}')
            with patch.object(config.sys, 'frozen', True, create=True), patch.object(config.sys, 'executable', str(source / 'DeskPet.exe')), patch.object(config, 'get_data_path', return_value=str(target)):
                config.prepare_data_directory()
            self.assertEqual((target / 'save.json').read_text(), 'new')
            self.assertTrue((target / 'words_A.json').exists())
            self.assertTrue((target / 'progress' / 'words_A.json').exists())


class CanvasTests(unittest.TestCase):
    def test_real_upload_cache_and_resource_cleanup(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        pygame.display.set_mode((32, 32), pygame.NOFRAME | pygame.HIDDEN)
        hwnd = window._get_hwnd()
        window._set_window_layered(hwnd)
        resources = ctypes.windll.user32.GetGuiResources
        resources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = wintypes.HANDLE
        baseline = resources(process(), 0)
        for _ in range(5):
            canvas = window._LayeredCanvas(hwnd, 32, 32)
            try:
                scene = pygame.Surface((32, 32), pygame.SRCALPHA)
                scene.fill((100, 150, 200, 128))
                self.assertTrue(canvas.present(scene, 100, 100))
                self.assertFalse(canvas.present(scene, 100, 100))
                self.assertTrue(canvas.present(scene, 110, 100))
            finally:
                canvas.close()
                canvas.close()
        self.assertEqual(resources(process(), 0), baseline)
