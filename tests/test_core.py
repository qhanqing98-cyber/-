import json
import os
import tempfile
import unittest

import words as words_module
from main import ContextMenu
from config import B_IDLE, B_WALK, BEHAVIOR_EVAL_INTERVAL, FPS
from pet import Pet


class PetBehaviorTests(unittest.TestCase):
    def test_looping_behavior_can_be_re_evaluated(self):
        pet = Pet()
        pet.behavior = B_IDLE
        pet.animation_finished = True
        pet.eval_timer = BEHAVIOR_EVAL_INTERVAL / FPS
        pet._choose_behavior = lambda: B_WALK

        pet.update(dt=1 / FPS)
        self.assertEqual(pet.behavior, B_WALK)
        self.assertTrue(pet.animation_finished)

        pet.eval_timer = BEHAVIOR_EVAL_INTERVAL / FPS
        pet._choose_behavior = lambda: B_IDLE
        pet.update(dt=1 / FPS)
        self.assertEqual(pet.behavior, B_IDLE)

    def test_position_is_clamped_vertically(self):
        pet = Pet()
        pet.y = -10000
        pet._clamp_position()
        self.assertEqual(pet.y, pet.min_y_scrn)


class WordListTests(unittest.TestCase):
    def test_delete_uses_all_books_not_only_loaded_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original = (
                words_module._DIR,
                words_module.INDEX_FILE,
                words_module.OLD_FILE,
            )
            try:
                words_module._DIR = temp_dir
                words_module.INDEX_FILE = os.path.join(temp_dir, 'words_index.json')
                words_module.OLD_FILE = os.path.join(temp_dir, 'words.json')
                names = ['A', 'B', 'C']
                for name in names:
                    with open(words_module._book_path(name), 'w', encoding='utf-8') as f:
                        json.dump({'words': [{'word': name, 'meaning': ''}], 'index': 0}, f)
                with open(words_module.INDEX_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'active_book': 'A', 'books': names}, f)

                word_list = words_module.WordList()
                self.assertEqual(len(word_list.books), 1)  # 验证确实是懒加载场景
                success, _ = word_list.delete_book('A')

                self.assertTrue(success)
                self.assertEqual(word_list.list_books(), ['B', 'C'])
                self.assertIn(word_list.active_book, ('B', 'C'))
            finally:
                (words_module._DIR,
                 words_module.INDEX_FILE,
                 words_module.OLD_FILE) = original


class ContextMenuTests(unittest.TestCase):
    def test_hovering_header_keeps_valid_hover_index(self):
        menu = ContextMenu()
        menu.show(100, 100, 0, 0)

        # 标题栏不对应菜单项，过去这里会把 hover_index 设为 None，
        # 随后的 draw() 在与整数比较时崩溃。
        menu.update_hover(menu.menu_x + 10, menu.menu_y + 10)
        self.assertEqual(menu.hover_index, -1)

    def test_grid_hit_testing_and_keyboard_navigation(self):
        menu = ContextMenu()
        menu.show(100, 100, 0, 0)
        target = menu._item_rect(3, screen_coords=True)
        self.assertEqual(menu.hit_test(*target.center), 'import_words')

        menu.show(100, 100, 0, 0)
        menu.move_grid(dy=1)
        self.assertEqual(menu.selected_index, 2)
        menu.move_grid(dx=1)
        self.assertEqual(menu.selected_index, 3)


if __name__ == '__main__':
    unittest.main()
