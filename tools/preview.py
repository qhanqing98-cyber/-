"""渲染三个 UI 状态供视觉检查，不创建桌面窗口，不读写存档。"""
from pathlib import Path
import sys
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import character
from config import WINDOW_WIDTH, WINDOW_HEIGHT, PET_CENTER_X, PET_CENTER_Y
from menus import ContextMenu
from pet import Pet


def preview():
    pygame.font.init()
    try:
        character.load_gifs()
        result = pygame.Surface((WINDOW_WIDTH * 3, WINDOW_HEIGHT + 40))
        result.fill((228, 234, 241))
        label_font = pygame.font.SysFont('Microsoft YaHei', 16)
        with patch.object(Pet, '_load'):
            pet = Pet()
        pet.animation_elapsed = 0.2
        for column, label in enumerate(('状态面板', '单词卡片', '右键菜单')):
            scene = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            character.draw_pet(scene, pet)
            if column == 0:
                pet.is_hovered = True
                character.draw_status(scene, pet)
                pet.is_hovered = False
            elif column == 1:
                pet.word_bubble_active = True
                character.draw_word_bubble(scene, {'word': 'performance',
                    'meaning': '性能；效率；表现。让每一次学习更顺畅。'}, '12/100')
            else:
                menu = ContextMenu()
                menu.show(PET_CENTER_X, PET_CENTER_Y - 170, 0, 0)
                menu.draw(scene, 0, 0)
            result.blit(scene, (column * WINDOW_WIDTH, 40))
            result.blit(label_font.render(label, True, (74, 88, 116)), (column * WINDOW_WIDTH + 16, 10))
        folder = ROOT / 'artifacts'
        folder.mkdir(exist_ok=True)
        pygame.image.save(result, str(folder / 'ui-preview.png'))
        return folder / 'ui-preview.png'
    finally:
        character._font_cache.clear()
        character._cached_word_bubble_layout.cache_clear()
        pygame.font.quit()


if __name__ == '__main__':
    print(preview())
