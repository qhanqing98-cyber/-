# words.py — 单词表管理
"""支持导入三种格式：纯文本（一行一个单词）、分隔符（ | 或 Tab）、JSON"""

import json
import os

WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'words.json')


class WordList:
    """管理单词列表的加载、保存、导入和进度"""

    def __init__(self):
        self.words = []   # [{"word": str, "meaning": str}, ...]
        self.index = 0    # 当前单词索引（循环）
        self._load()

    # ── 持久化 ────────────────────────────────

    def _load(self):
        if not os.path.exists(WORDS_FILE):
            return
        try:
            with open(WORDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.words = data.get('words', [])
            self.index = data.get('index', 0)
            if self.index >= len(self.words) and self.words:
                self.index = 0
        except Exception:
            pass

    def save(self):
        try:
            with open(WORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'words': self.words, 'index': self.index},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 查询 ──────────────────────────────────

    def has_words(self):
        return len(self.words) > 0

    def get_current(self):
        """返回当前要显示的单词 dict，如果没有则返回 None"""
        if not self.words or self.index >= len(self.words):
            return None
        return self.words[self.index]

    def advance(self):
        """移到下一个单词（循环）并保存"""
        if not self.words:
            return
        self.index = (self.index + 1) % len(self.words)
        self.save()

    # ── 导入 ──────────────────────────────────

    def import_file(self, path):
        """导入单词表，自动识别格式。返回 (success: bool, message: str)"""
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

        self.words = new_words
        self.index = 0
        self.save()
        return True, f"成功导入 {len(new_words)} 个单词"

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
            # 自动检测分隔符优先级: | > Tab > 逗号 > 纯单词
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
