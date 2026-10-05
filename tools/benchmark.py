"""在临时目录比较整本写入与进度写入，输出本机实际测量结果。"""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import character
import storage
import words


def measure(action, count=10):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(samples), 3)


def benchmark():
    largest = max((p for p in ROOT.glob('words_*.json') if p.name != 'words_index.json'),
                  key=lambda p: p.stat().st_size)
    data = json.loads(largest.read_text(encoding='utf-8'))
    # 同时检查真实内置词库的格式。
    for book in ROOT.glob('words_*.json'):
        if book.name != 'words_index.json':
            words._normalize_words(json.loads(book.read_text(encoding='utf-8'))['words'])
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'words_benchmark.json'
        storage.write_json_atomic(target, data)
        with patch.object(words, '_DIR', folder), patch.object(words, 'INDEX_FILE', str(Path(folder) / 'words_index.json')), patch.object(words, 'OLD_FILE', str(Path(folder) / 'words.json')):
            manager = words.WordList()
            old_ms = measure(lambda: storage.write_json_atomic(target, data))
            progress_ms = measure(manager.advance)
            progress_bytes = Path(words._progress_path('benchmark')).stat().st_size
        pygame.font.init()
        try:
            item = {'word': 'performance', 'meaning': '性能；效率；表现'}
            def cold_layout():
                character._cached_word_bubble_layout.cache_clear()
                character.get_word_bubble_rect(item, '1/100')
            cold_ms = measure(cold_layout, 100)
            warm_ms = measure(lambda: character.get_word_bubble_rect(item, '1/100'), 100)
        finally:
            character._font_cache.clear()
            pygame.font.quit()
        return {'largest_book': largest.name, 'book_bytes': target.stat().st_size,
                'progress_bytes': progress_bytes, 'full_write_median_ms': old_ms,
                'progress_write_median_ms': progress_ms,
                'card_layout_cold_median_ms': cold_ms,
                'card_layout_cached_median_ms': warm_ms}


if __name__ == '__main__':
    report = benchmark()
    print(json.dumps(report, ensure_ascii=False, indent=2))
