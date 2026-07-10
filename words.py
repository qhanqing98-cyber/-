# words.py — 多单词本管理（每本独立文件）
"""支持多个单词本，各本存为独立文件，避免大文件卡顿。"""

import json
import os

from config import get_data_path, get_resource_path

_DIR = get_data_path()
INDEX_FILE = os.path.join(_DIR, 'words_index.json')
OLD_FILE = os.path.join(_DIR, 'words.json')


def _book_path(name):
    """返回单词本文件的路径"""
    return os.path.join(_DIR, f'words_{name}.json')


class WordList:
    """管理多个单词本的加载、保存、导入和切换（每本独立文件）"""

    def __init__(self):
        self.books = {}          # {"书名": {"words": [...], "index": 0}, ...}
        self.active_book = None  # 当前激活的单词本名
        self._dirty = False      # 当前本是否有未保存的改动
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
        """加载 index 文件，兼容旧 words.json；出错时扫描文件系统恢复"""
        # 第1步：尝试加载新格式 index
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    idx = json.load(f)
                active = idx.get('active_book', '')
                book_names = idx.get('books', [])
                if not isinstance(book_names, list):
                    book_names = []
                if active and active in book_names:
                    self._load_book(active)
                elif book_names:
                    self._load_book(book_names[0])
                else:
                    self.books = {'默认': {'words': [], 'index': 0}}
                    self.active_book = '默认'
                return
            except Exception as e:
                print(f"[words] 索引文件损坏({e})，尝试扫描文件系统恢复...")

        # 第2步：尝试从旧 words.json 迁移
        if os.path.exists(OLD_FILE):
            try:
                with open(OLD_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if 'books' in data:
                    for name, book in data['books'].items():
                        self._save_one_book(name, book)
                    active = data.get('active_book', list(data['books'].keys())[0] if data['books'] else '默认')
                    self._write_index(active, list(data['books'].keys()))
                    os.remove(OLD_FILE)
                    self._load_book(active)
                    return

                old_words = data.get('words', [])
                old_index = data.get('index', 0)
                self._save_one_book('默认', {'words': old_words, 'index': old_index})
                self._write_index('默认', ['默认'])
                os.remove(OLD_FILE)
                self._load_book('默认')
                return
            except Exception as e:
                print(f"[words] 旧格式迁移失败: {e}")

        # 第3步：扫描文件系统恢复单词本
        scanned = self._scan_books()
        if scanned:
            first = scanned[0]
            self._load_book(first)
            self._write_index(first, scanned)
            print(f"[words] 从文件系统恢复了 {len(scanned)} 个单词本")
            return

        # 第4步：尝试从打包资源复制初始单词本（仅打包模式生效）
        if self._copy_bundled_books():
            scanned = self._scan_books()
            if scanned:
                first = scanned[0]
                self._load_book(first)
                self._write_index(first, scanned)
                print(f"[words] 从打包资源复制了 {len(scanned)} 个单词本")
                return

        # 没有任何数据 → 创建默认空本
        self.books = {'默认': {'words': [], 'index': 0}}
        self.active_book = '默认'
        self._save_one_book('默认', self.books['默认'])
        self._write_index('默认', ['默认'])

    def _copy_bundled_books(self):
        """首次运行时，将打包在 exe 内的单词本文件复制到数据目录（仅打包模式有效）"""
        res_dir = get_resource_path()
        if res_dir == _DIR:
            return False  # 源码模式，无需复制
        copied = False
        for fname in os.listdir(res_dir):
            if fname.startswith('words_') and fname.endswith('.json'):
                dst = os.path.join(_DIR, fname)
                if not os.path.exists(dst):
                    src = os.path.join(res_dir, fname)
                    try:
                        with open(src, 'rb') as sf, open(dst, 'wb') as df:
                            df.write(sf.read())
                        copied = True
                    except Exception:
                        pass
        return copied

    def _load_book(self, name):
        """加载指定单词本到内存。文件不存在时创建空本。"""
        path = _book_path(name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.books[name] = data
            except Exception as e:
                print(f"[words] 加载单词本「{name}」失败({e})，创建空本")
                self.books[name] = {'words': [], 'index': 0}
        else:
            print(f"[words] 单词本文件「{name}」不存在，创建空本")
            self.books[name] = {'words': [], 'index': 0}
        self.active_book = name
        self._dirty = False

    def _save_one_book(self, name, data):
        """写入单个单词本文件。返回成功与否。"""
        path = _book_path(name)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[words] 保存单词本「{name}」失败: {e}")
            return False

    def _save_active_book(self):
        """保存当前激活的单词本。返回成功与否。"""
        if self.active_book and self.active_book in self.books:
            ok = self._save_one_book(self.active_book, self.books[self.active_book])
            if ok:
                self._dirty = False
            return ok
        return False

    def _write_index(self, active, book_names):
        """写入 index 文件。返回成功与否。"""
        try:
            with open(INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump({'active_book': active, 'books': book_names},
                          f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[words] 保存索引文件失败: {e}")
            return False

    def save(self):
        """持久化当前单词本 + index（合并已有索引，防止覆盖其他单词本）"""
        self._save_active_book()
        # 读取已有索引，合并当前内存中的单词本
        existing_books = set()
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    idx = json.load(f)
                existing_books = set(idx.get('books', []))
            except Exception:
                pass
        # 只保留文件确实存在的（过滤掉已被删除的）
        existing_books = {b for b in existing_books if os.path.exists(_book_path(b))}
        all_books = existing_books | set(self.books.keys())
        self._write_index(self.active_book, list(all_books))

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
        """列出所有已知单词本（内存 + 文件系统扫描）"""
        mem = set(self.books.keys())
        # 也从索引文件中读取
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    idx = json.load(f)
                mem.update(idx.get('books', []))
            except Exception:
                pass
        # 也扫描文件系统
        mem.update(self._scan_books())
        return sorted(mem)

    def _scan_books(self):
        """扫描 filesystem 获取所有单词本名"""
        names = []
        prefix = 'words_'
        suffix = '.json'
        for fname in os.listdir(_DIR):
            if fname.startswith(prefix) and fname.endswith(suffix) and fname != 'words_index.json':
                name = fname[len(prefix):-len(suffix)]
                names.append(name)
        return names

    # ── 切换单词本 ─────────────────────────────

    def switch_book(self, name):
        if name in self.books:
            # 保存当前本
            self._save_active_book()
            # 如果目标本不在内存中，从文件加载
            if name not in self.books:
                self._load_book(name)
            else:
                self.active_book = name
            self.save()
            return True
        # 如果在文件系统但不在内存
        path = _book_path(name)
        if os.path.exists(path):
            self._save_active_book()
            self._load_book(name)
            self.save()
            return True
        return False

    def delete_book(self, name):
        """删除指定单词本（含文件）。返回 (success, message)"""
        # 如果不在内存中，尝试从文件加载
        if name not in self.books:
            path = _book_path(name)
            if os.path.exists(path):
                self._load_book(name)
            else:
                return False, f"单词本「{name}」不存在"

        if len(self.books) <= 1:
            return False, "至少保留一个单词本"
        # 删除文件
        path = _book_path(name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                return False, f"删除文件失败: {e}"
        del self.books[name]
        # 如果删的是当前激活的本，切到另一个
        if self.active_book == name:
            new_active = next(iter(self.books.keys()))
            self._load_book(new_active)
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

        if not book_name:
            book_name = os.path.splitext(os.path.basename(path))[0]

        # 保护：单词本名不能是 "index"（会与索引文件冲突）
        if book_name == 'index':
            book_name = 'index_book'

        # 保存当前本
        self._save_active_book()

        # 添加并切换到新本
        self.books[book_name] = {'words': new_words, 'index': 0}
        self.active_book = book_name

        # 先写入单词本文件
        if not self._save_one_book(book_name, self.books[book_name]):
            return False, f"保存单词本「{book_name}」失败，请检查磁盘空间或权限"

        # 用 save() 写入索引（会自动合并已有单词本）
        self.save()

        # 验证写入成功
        if not os.path.exists(_book_path(book_name)):
            return False, f"单词本文件未能成功写入"

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
