"""用实际绘制代码导出互动预览，不创建桌面窗口、不读取或保存用户数据。"""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
from PIL import Image
import character
from pet import Pet


def preview():
    pygame.font.init()
    try:
        character.load_gifs()
        with patch.object(Pet, '_load'):
            pet = Pet()
        width, height = 290, 320
        font = pygame.font.SysFont('Microsoft YaHei', 18)
        names = (('happy', '点击 · 开心'), ('petting', '抚摸 · 摸头'), ('lift', '拖动 · 提起'))
        folder = ROOT / 'artifacts'
        folder.mkdir(exist_ok=True)
        sheet = pygame.Surface((width * 4, height * 3))
        sheet.fill((236, 235, 240))
        for row, (name, label) in enumerate(names):
            for col, elapsed in enumerate((0, 0.2, 0.5, 0.8)):
                frame = character._sprite_cache[name][character.animation_frame_index(name, elapsed)]
                sheet.blit(frame, frame.get_rect(center=(col * width + width // 2, row * height + 180)))
                sheet.blit(font.render(f'{label}  {elapsed:.1f}s', True, (74, 92, 124)), (col * width + 15, row * height + 15))
        pygame.image.save(sheet, str(folder / 'interaction-preview.png'))
        animated = []
        for index in range(36):
            canvas = pygame.Surface((width * 3, height))
            canvas.fill((236, 235, 240))
            for col, (name, label) in enumerate(names):
                elapsed = min(index / 30, character._frame_end_times[name][-1] - 1 / 30)
                frame = character._sprite_cache[name][character.animation_frame_index(name, elapsed)]
                canvas.blit(frame, frame.get_rect(center=(col * width + width // 2, 180)))
                canvas.blit(font.render(label, True, (74, 92, 124)), (col * width + 15, 15))
            animated.append(Image.frombytes('RGB', canvas.get_size(), pygame.image.tobytes(canvas, 'RGB')))
        animated[0].save(folder / 'interaction-preview.gif', save_all=True, append_images=animated[1:], duration=33, loop=0)
        return folder / 'interaction-preview.png'
    finally:
        character._font_cache.clear()
        character._cached_word_bubble_layout.cache_clear()
        pygame.font.quit()


if __name__ == '__main__':
    print(preview())
