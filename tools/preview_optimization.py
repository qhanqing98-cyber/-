"""预览屏幕边缘布局与暂停状态，使用实际绘制函数和临时宠物。"""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import character
from pet import Pet


def preview():
    pygame.font.init()
    try:
        character.load_gifs()
        with patch.object(Pet, '_load'):
            pet = Pet()
        font = pygame.font.SysFont('Microsoft YaHei', 16)
        result = pygame.Surface((1350, 540))
        result.fill((236, 235, 240))
        states = (('安静模式 · 右上边缘', (350, 140), '安静中'),
                  ('暂停剩余时间 · 左下边缘', (100, 390), '暂停·12分钟'),
                  ('单词卡片 · 左上边缘', (100, 140), None))
        pet.is_hovered = True
        for index, (label, center, mode) in enumerate(states):
            scene = pygame.Surface((450, 500), pygame.SRCALPHA)
            character.draw_pet(scene, pet, center)
            if mode:
                character.draw_status(scene, pet, center, mode)
            else:
                character.draw_word_bubble(scene, {'word': 'performance', 'meaning': '性能；效率。减少重复绘制，让桌宠更轻盈。'}, '12/100', center)
            result.blit(scene, (index * 450, 40))
            result.blit(font.render(label, True, (74, 92, 124)), (index * 450 + 16, 10))
        target = ROOT / 'artifacts' / 'optimization-preview.png'
        target.parent.mkdir(exist_ok=True)
        pygame.image.save(result, str(target))
        return target
    finally:
        character._font_cache.clear()
        character._cached_word_bubble_layout.cache_clear()
        pygame.font.quit()


if __name__ == '__main__':
    print(preview())
