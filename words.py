"""词库与学习进度分开保存；切词只写很小的进度文件。"""
import csv
import io
import json
import os
import shutil
from config import get_data_path, get_resource_path
from storage import backup_corrupt, finite_number, log, write_json_atomic

_DIR = get_data_path()
INDEX_FILE = os.path.join(_DIR, 'words_index.json')
OLD_FILE = os.path.join(_DIR, 'words.json')
_write_json_atomic = write_json_atomic


def _valid_name(name):
    return (isinstance(name, str) and bool(name.strip()) and name.casefold() != 'index'
            and not any(c in name for c in '<>:"/\\|?*')
            and not any(ord(c) < 32 for c in name) and not name.endswith('.')
            and len(name) <= 100)


def _book_path(name):
    if not _valid_name(name):
        raise ValueError('单词本名称包含非法字符或使用了保留名称')
    return os.path.join(_DIR, f'words_{name}.json')


def _progress_path(name):
    _book_path(name)
    return os.path.join(_DIR, 'progress', f'words_{name}.json')


def _normalize_words(items):
    if not isinstance(items, list):
        raise ValueError('words 必须是列表')
    words, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('每个单词必须是对象')
        word, meaning = item.get('word'), item.get('meaning', '')
        if not isinstance(word, str) or not isinstance(meaning, str):
            raise ValueError('word 和 meaning 必须是字符串')
        word, meaning = word.strip(), meaning.strip()
        if word and (word, meaning) not in seen:
            seen.add((word, meaning))
            words.append({'word': word, 'meaning': meaning})
    return words


class WordList:
    def __init__(self):
        self.books = {}
        self.active_book = None
        self._content_dirty = set()
        self._progress_dirty = set()
        self._blocked_books = set()
        self._index_dirty = False
        self.last_error = ''
        self._load_or_migrate()

    @property
    def words(self):
        return self.books.get(self.active_book, {}).get('words', [])

    @words.setter
    def words(self, value):
        if self.active_book in self.books:
            self.books[self.active_book]['words'] = _normalize_words(value)
            self._content_dirty.add(self.active_book)
            self.index = self.index

    @property
    def index(self):
        return self.books.get(self.active_book, {}).get('index', 0)

    @index.setter
    def index(self, value):
        if self.active_book in self.books:
            self.books[self.active_book]['index'] = self._safe_index(value, len(self.words))
            self._progress_dirty.add(self.active_book)

    @staticmethod
    def _safe_index(value, count):
        return int(finite_number(value, 0, 0)) % count if count else 0

    def _error(self, message):
        self.last_error = message
        log.error(message)
        return False

    def _load_or_migrate(self):
        os.makedirs(_DIR, exist_ok=True)
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, encoding='utf-8-sig') as stream:
                    data = json.load(stream)
                names = data['books']
                if not isinstance(names, list) or not all(_valid_name(n) for n in names):
                    raise ValueError('索引中的单词本名称无效')
                names = [n for n in names if os.path.exists(_book_path(n))]
                if names:
                    active = data.get('active_book')
                    self._load_book(active if active in names else names[0])
                    return
            except (OSError, ValueError, KeyError, TypeError):
                log.exception('索引读取失败，将扫描词库恢复')
                try:
                    backup_corrupt(INDEX_FILE)
                except OSError:
                    self._index_blocked = True
        if os.path.exists(OLD_FILE):
            try:
                with open(OLD_FILE, encoding='utf-8-sig') as stream:
                    data = json.load(stream)
                legacy = data.get('books', {'默认': data})
                normalized = {}
                for name, book in legacy.items():
                    _book_path(name)
                    words = _normalize_words(book.get('words', []))
                    normalized[name] = {'words': words, 'index': self._safe_index(book.get('index', 0), len(words))}
                if not normalized:
                    raise ValueError('旧词库为空')
                for name, book in normalized.items():
                    if os.path.exists(_book_path(name)):
                        continue  # 迁移重试时保留已存在的新词库。
                    if not self._save_one_book(name, book):
                        raise OSError(self.last_error)
                active = data.get('active_book')
                if active not in normalized:
                    active = next(iter(normalized))
                if not self._write_index(active, list(normalized)):
                    raise OSError(self.last_error)
                shutil.copy2(OLD_FILE, OLD_FILE + '.migrated.bak')
                os.remove(OLD_FILE)
                self._load_book(active)
                return
            except (OSError, ValueError, TypeError, AttributeError):
                log.exception('旧词库迁移失败，原文件保留')
        scanned = self._scan_books()
        if not scanned:
            self._copy_bundled_books()
            scanned = self._scan_books()
        if scanned:
            self._load_book(scanned[0])
        else:
            self.active_book = '默认'
            self.books['默认'] = {'words': [], 'index': 0}
            self._content_dirty.add('默认')
        self._index_dirty = True
        self.save()

    def _copy_bundled_books(self):
        res_dir = get_resource_path()
        if os.path.abspath(res_dir) == os.path.abspath(_DIR):
            return False
        copied = False
        for filename in os.listdir(res_dir):
            if filename.startswith('words_') and filename.endswith('.json') and filename != 'words_index.json':
                target = os.path.join(_DIR, filename)
                if not os.path.exists(target):
                    try:
                        shutil.copy2(os.path.join(res_dir, filename), target)
                        copied = True
                    except OSError:
                        log.exception('内置词库复制失败：%s', filename)
        return copied

    def _load_book(self, name):
        path = _book_path(name)
        book = {'words': [], 'index': 0}
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8-sig') as stream:
                    data = json.load(stream)
                words = _normalize_words(data['words'])
                book = {'words': words, 'index': self._safe_index(data.get('index', 0), len(words))}
            except (OSError, ValueError, KeyError, TypeError):
                self._error(f'单词本「{name}」损坏，请从备份恢复或重新导入')
                self._blocked_books.add(name)
                try:
                    backup_corrupt(path)
                except OSError:
                    log.exception('损坏词库备份失败')
        progress = _progress_path(name)
        if os.path.exists(progress):
            try:
                with open(progress, encoding='utf-8') as stream:
                    saved = json.load(stream)
                book['index'] = self._safe_index(saved['index'], len(book['words']))
            except (OSError, ValueError, KeyError, TypeError):
                log.exception('学习进度损坏，恢复词库原始进度')
                try:
                    backup_corrupt(progress)
                except OSError:
                    self._blocked_books.add(name)
        self.books[name] = book
        self.active_book = name

    def _save_one_book(self, name, data):
        if name in self._blocked_books:
            return self._error(f'单词本「{name}」损坏，已禁止自动覆盖')
        try:
            _write_json_atomic(_book_path(name), data)
            self._content_dirty.discard(name)
            return True
        except (OSError, ValueError):
            return self._error(f'保存单词本「{name}」失败，请检查磁盘空间或权限')

    def _save_progress(self, name):
        if name in self._blocked_books:
            return False
        try:
            _write_json_atomic(_progress_path(name), {'index': self.books[name]['index']})
            self._progress_dirty.discard(name)
            return True
        except (OSError, ValueError):
            return self._error(f'保存「{name}」学习进度失败，将在下次保存时重试')

    def _save_active_book(self):
        name = self.active_book
        if name not in self.books:
            return False
        if name in self._content_dirty and not self._save_one_book(name, self.books[name]):
            return False
        return self._save_progress(name) if name in self._progress_dirty else True

    def _write_index(self, active, book_names):
        if getattr(self, '_index_blocked', False):
            return self._error('索引备份失败，已禁止自动覆盖')
        try:
            _write_json_atomic(INDEX_FILE, {'active_book': active, 'books': sorted(book_names)})
            self._index_dirty = False
            return True
        except (OSError, ValueError):
            return self._error('保存词库索引失败，将在下次保存时重试')

    def save(self):
        """只写发生变化的数据；失败的项目继续保留待保存标记。"""
        ok = True
        for name in list(self._content_dirty):
            ok = self._save_one_book(name, self.books[name]) and ok
        for name in list(self._progress_dirty):
            ok = self._save_progress(name) and ok
        if self._index_dirty:
            ok = self._write_index(self.active_book, self.list_books()) and ok
        if ok and not self._blocked_books:
            self.last_error = ''
        return ok

    def has_words(self):
        return bool(self.words)

    def get_current(self):
        return self.words[self.index] if self.words else None

    def advance(self):
        if not self.words:
            return True
        self.index = self.index + 1
        return self._save_progress(self.active_book)

    def get_active_book_name(self):
        return self.active_book or ''

    def list_books(self):
        return sorted(set(self.books) | set(self._scan_books()))

    def _scan_books(self):
        return sorted(filename[6:-5] for filename in os.listdir(_DIR)
                      if filename.startswith('words_') and filename.endswith('.json')
                      and _valid_name(filename[6:-5]))

    def switch_book(self, name):
        if not _valid_name(name) or name not in self.list_books():
            return False
        if not self.save():
            return False
        if name not in self.books:
            self._load_book(name)
        else:
            self.active_book = name
        self._index_dirty = True
        return self.save()

    def delete_book(self, name):
        names = self.list_books()
        if name not in names:
            return False, f'单词本「{name}」不存在'
        if len(names) <= 1:
            return False, '至少保留一个单词本'
        try:
            if os.path.exists(_book_path(name)):
                os.remove(_book_path(name))
            if os.path.exists(_progress_path(name)):
                os.remove(_progress_path(name))
        except OSError as error:
            return False, f'删除文件失败：{error}'
        self.books.pop(name, None)
        self._blocked_books.discard(name)
        self._content_dirty.discard(name)
        self._progress_dirty.discard(name)
        if self.active_book == name:
            self._load_book(next(n for n in names if n != name))
        self._index_dirty = True
        if not self.save():
            return False, '文件已删除，但索引保存失败，请重试保存'
        return True, f'已删除「{name}」'

    def import_file(self, path, book_name=None):
        try:
            with open(path, encoding='utf-8-sig') as stream:
                content = stream.read()
        except (OSError, UnicodeError) as error:
            return False, f'读取文件失败：{error}'
        ext = os.path.splitext(path)[1].lower()
        if ext == '.json':
            ok, result = self._parse_json(content)
            if not ok:
                return False, result
            new_words = result
        else:
            try:
                new_words = self._parse_csv(content) if ext == '.csv' else self._parse_text(content)
            except csv.Error as error:
                return False, f'CSV 解析失败：{error}'
        if not new_words:
            return False, '未找到有效单词'
        name = book_name or os.path.splitext(os.path.basename(path))[0]
        if isinstance(name, str) and name.casefold() == 'index':
            name = 'index_book'
        if not _valid_name(name):
            return False, '单词本名称包含非法字符或过长'
        base, number = name, 2
        known = {n.casefold() for n in self.list_books()}
        while name.casefold() in known:
            suffix = f' ({number})'
            name = base[:100 - len(suffix)] + suffix
            number += 1
        if not self.save():
            return False, self.last_error
        book = {'words': new_words, 'index': 0}
        if not self._save_one_book(name, book):
            return False, self.last_error
        self.books[name] = book
        self.active_book = name
        self._index_dirty = True
        if not self.save():
            return False, f'词库已保存，但索引保存失败：{self.last_error}'
        return True, f'成功导入 {len(new_words)} 个单词到「{name}」'

    def _parse_json(self, content):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                data = data['words'] if 'words' in data else [data]
            words = _normalize_words(data)
            if not words:
                raise ValueError('未找到有效单词')
            return True, words
        except (ValueError, TypeError, KeyError) as error:
            return False, f'JSON 解析失败：{error}'

    def _parse_csv(self, content):
        rows = list(csv.reader(io.StringIO(content), strict=True))
        if rows and [s.strip().lower() for s in rows[0][:2]] == ['word', 'meaning']:
            rows = rows[1:]
        return _normalize_words([{'word': row[0], 'meaning': ','.join(row[1:])}
                                 for row in rows if row and row[0].strip()])

    def _parse_text(self, content):
        items = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            separator = next((s for s in ('|', '\t', ',') if s in line), None)
            parts = line.split(separator, 1) if separator else [line]
            items.append({'word': parts[0], 'meaning': parts[1] if len(parts) > 1 else ''})
        return _normalize_words(items)
