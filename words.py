# words.py — 多单词本管理
"""支持多个单词本，每个独立记录进度。导入自动加为新本，可自由切换。"""

import json
import os

WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'words.json')


class WordList:
    """管理多个单词本的加载、保存、导入和切换"""

    def __init__(self):
        self.books = {}          # {"书名": {"words": [...], "index": 0}, ...}
        self.active_book = None  # 当前激活的单词本名
        self._load_or_migrate()

    # ── 当前书快捷属性 ─────────────────────────

    @property
    def words(self):
        if self.active_book and self.active_book in self.books:
            return self.books[self.active_book]['words']
        return []

    @words.setter
    def words(self, val):
        if self.active_book and self.active_book in self.books:
            self.books[self.active_book]['words'] = val

    @property
    def index(self):
        if self.active_book and self.active_book in self.books:
            return self.books[self.active_book]['index']
        return 0

    @index.setter
    def index(self, val):
        if self.active_book and self.active_book in self.books:
            self.books[self.active_book]['index'] = val

    # ── 持久化 ────────────────────────────────

    def _load_or_migrate(self):
        """加载 words.json，兼容旧格式"""
        if not os.path.exists(WORDS_FILE):
            # 创建默认空本
            self.books = {'默认': {'words': [], 'index': 0}}
            self.active_book = '默认'
            return

        try:
            with open(WORDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            self.books = {'默认': {'words': [], 'index': 0}}
            self.active_book = '默认'
            return

        # 新格式：有 "books" 键
        if 'books' in data:
            self.books = data['books']
            self.active_book = data.get('active_book', list(self.books.keys())[0] if self.books else None)
            return

        # 旧格式：{"words": [...], "index": N} → 迁移到 "默认" 本
        old_words = data.get('words', [])
        old_index = data.get('index', 0)
        self.books = {'默认': {'words': old_words, 'index': old_index}}
        self.active_book = '默认'
        # 立即保存为新格式
        self.save()

    def save(self):
        try:
            with open(WORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'active_book': self.active_book,
                    'books': self.books,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 查询 ──────────────────────────────────

    def has_words(self):
        return len(self.words) > 0

    def get_current(self):
        if not self.words or self.index >= len(self.words):
            return None
        return self.words[self.index]

    def advance(self):
        if not self.words:
            return
        self.index = (self.index + 1) % len(self.words)
        self.save()

    def get_active_book_name(self):
        return self.active_book or ''

    def list_books(self):
        return list(self.books.keys())

    # ── 切换单词本 ─────────────────────────────

    def switch_book(self, name):
        if name in self.books:
            self.active_book = name
            self.save()
            return True
        return False

    def delete_book(self, name):
        """删除指定单词本。返回 (success, message)"""
        if name not in self.books:
            return False, f"单词本「{name}」不存在"
        if len(self.books) <= 1:
            return False, "至少保留一个单词本"
        del self.books[name]
        # 如果删的是当前激活的本，切到另一个
        if self.active_book == name:
            self.active_book = next(iter(self.books.keys()))
        self.save()
        return True, f"已删除「{name}」"

    # ── 导入 ──────────────────────────────────

    def import_file(self, path, book_name=None):
        """导入单词表为新单词本。返回 (success, message)"""
        if not os.path.exists(path):
            return False, "文件不存在"

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, f"读取文件失败: {e}"

        ext = os.path.splitext(path)[1].lower()
        new_words = []

        if ext == '.json':
            ok, result = self._parse_json(content)
            if not ok:
                return False, result
            new_words = result
        else:
            new_words = self._parse_text(content)

        if not new_words:
            return False, "未找到有效单词"

        # 确定单词本名称
        if not book_name:
            book_name = os.path.splitext(os.path.basename(path))[0]

        # 添加或覆盖
        self.books[book_name] = {'words': new_words, 'index': 0}
        self.active_book = book_name
        self.save()
        return True, f"成功导入 {len(new_words)} 个单词到「{book_name}」"

    def _parse_json(self, content):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {e}"

        words = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    w = item.get('word', '').strip()
                    m = item.get('meaning', '').strip()
                    if w:
                        words.append({'word': w, 'meaning': m})
        elif isinstance(data, dict):
            w = data.get('word', '').strip()
            m = data.get('meaning', '').strip()
            if w:
                words.append({'word': w, 'meaning': m})

        if not words:
            return False, "JSON 格式应为 [{\"word\":\"...\",\"meaning\":\"...\"}]"
        return True, words

    def _parse_text(self, content):
        words = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if '|' in line:
                parts = line.split('|', 1)
                w, m = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''
            elif '\t' in line:
                parts = line.split('\t', 1)
                w, m = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''
            elif ',' in line:
                parts = line.split(',', 1)
                w, m = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''
            else:
                w, m = line, ''
            if w:
                words.append({'word': w, 'meaning': m})
        return words
