"""测量像素缓存及静态画面上传路径，不接触用户存档。"""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import character
import window


def benchmark():
    started = time.perf_counter()
    character.load_gifs()
    decode_seconds = time.perf_counter() - started
    initial = character.animation_memory_bytes()
    first_interaction = {}
    for name in ('happy', 'petting', 'lift'):
        started = time.perf_counter()
        character._sprite_cache[name][0]
        character._flipped_cache[name][0]
        first_interaction[name] = round((time.perf_counter() - started) * 1000, 3)
    peak = character.animation_memory_bytes()
    for name, frames in character._sprite_cache.items():
        for index in range(len(frames)):
            frames[index]
            character._flipped_cache[name][index]
            peak = max(peak, character.animation_memory_bytes())
    pygame.display.init()
    canvas = None
    try:
        pygame.display.set_mode((450, 500), pygame.NOFRAME | pygame.HIDDEN)
        hwnd = window._get_hwnd()
        window._set_window_layered(hwnd)
        canvas = window._LayeredCanvas(hwnd, 450, 500)
        scene = pygame.Surface((450, 500), pygame.SRCALPHA)
        scene.fill((120, 140, 170, 128))
        canvas.present(scene, 100, 100)
        timings = {}
        for changed in (True, False):
            started = time.perf_counter()
            for _ in range(100):
                canvas.present(scene, 100, 100, content_changed=changed)
            timings[str(changed)] = round((time.perf_counter() - started) * 1000, 3)
        return {'decode_seconds': round(decode_seconds, 3),
                'initial_sprite_cache_mib': round(initial / 1024**2, 2),
                'peak_sprite_cache_mib': round(peak / 1024**2, 2),
                'first_interaction_and_flip_ms': first_interaction,
                'static_present_100_calls_with_pixel_comparison_ms': timings['True'],
                'static_present_100_calls_with_scene_key_ms': timings['False']}
    finally:
        if canvas:
            canvas.close()
        pygame.display.quit()


if __name__ == '__main__':
    report = benchmark()
    folder = ROOT / 'artifacts'
    folder.mkdir(exist_ok=True)
    (folder / 'optimization-benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
