# -*- coding: utf-8 -*-
# main.py — 桌宠主程序
# 启动: python main.py  或双击 run_pet.bat

import ctypes
from ctypes import wintypes
import os
import sys
import traceback

import pygame

from config import *
from pet import Pet
from words import WordList
import character


def _install_crash_logger():
    """pythonw 启动时没有控制台，未捕获异常会静默退出；
    挂上钩子把堆栈写进 crash.log 方便排查。"""
    def _hook(exc_type, exc, tb):
        try:
            with open(os.path.join(get_data_path(), 'crash.log'),
                      'a', encoding='utf-8') as f:
                f.write('\n' + '-' * 60 + '\n')
                f.write('\n'.join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass
    sys.excepthook = _hook

# ─── Windows API 常量 ────────────────────────
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_SWP_NOZORDER = 0x0004
_LWA_COLORKEY = 1

_VK_LBUTTON = 0x01

_user32 = ctypes.windll.user32


def _rgb(r, g, b):
    return ctypes.c_uint(r | (g << 8) | (b << 16)).value


def _get_hwnd():
    return pygame.display.get_wm_info()['window']


# 显式声明 64 位指针类型，避免句柄被截断导致比较失配
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


def _window_focused(hwnd):
    """窗口是否持有键盘焦点（键盘交互的前提）"""
    return _user32.GetForegroundWindow() == hwnd


def _set_window_transparent(hwnd):
    current = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    style = current | _WS_EX_LAYERED | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW
    _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
    _user32.SetLayeredWindowAttributes(
        hwnd, _rgb(*TRANSPARENT_COLOR), 0, _LWA_COLORKEY)


def _set_clickthrough(hwnd, enabled):
    current = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    if enabled:
        _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                               current | _WS_EX_TRANSPARENT)
    else:
        _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                               current & ~_WS_EX_TRANSPARENT)


def _move_window(hwnd, x, y):
    _user32.SetWindowPos(hwnd, 0,
                         int(x), int(y),
                         WINDOW_WIDTH, WINDOW_HEIGHT,
                         _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)


def _get_cursor_screen_pos():
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _is_lbutton_pressed():
    """全局检测左键是否按下（不依赖窗口焦点）"""
    return (_user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000) != 0


def _blit_rounded(surf, color, rect, radius, width=0):
    """在 SRCALPHA 临时面上画半透明圆角矩形后贴回 surf。
    直接在显示面上用 RGBA 色调用 pygame.draw 会被忽略 alpha，
    所以需要临时面来保证半透明效果。"""
    x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    if w <= 0 or h <= 0:
        return
    temp = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(temp, color, temp.get_rect(), width, border_radius=radius)
    surf.blit(temp, (x, y))


# ─── 右键菜单 ────────────────────────────────

class ContextMenu:
    def __init__(self):
        self.active = False
        self.menu_x = 0
        self.menu_y = 0
        self.item_h = 46
        self.item_w = 126
        self.item_gap = 6
        self.quit_h = 34
        self.header_h = 38
        self.pad = 8
        self.max_visible = 7
        self.scroll_offset = 0
        self.selected_index = 0
        self.items = [
            ('喂食', 'feed', '恢复饱食度'),
            ('摸摸它', 'pet', '提升心情'),
            ('选择单词本', 'switch_book', '切换学习内容'),
            ('导入单词表', 'import_words', 'TXT / CSV / JSON'),
            ('设置单词间隔', 'set_interval', '调整提醒频率'),
            ('删除单词本', 'delete_book', '管理本地词库'),
            ('退出桌宠', 'quit', '保存并退出'),
        ]
        self.font = None
        self.hint_font = None
        self.title_font = None
        self.hover_index = -1

    @property
    def _visible_count(self):
        return len(self.items)

    @property
    def _menu_w(self):
        return self.item_w * 2 + self.item_gap + self.pad * 2

    @property
    def _menu_h(self):
        return (self.header_h + self.pad * 2 + self.item_h * 3 +
                self.item_gap * 3 + self.quit_h)

    @property
    def _items_top(self):
        return self.menu_y + self.pad + self.header_h

    def show(self, sx, sy, win_l, win_t):
        """弹出菜单，自动避免超出窗口边界"""
        self.active = True
        self.selected_index = 0
        self.scroll_offset = 0

        w = self._menu_w
        h = self._menu_h

        # 转为窗口相对坐标
        rx = sx - win_l
        ry = sy - win_t

        # 垂直：优先放光标下方，放不下则放上方
        if ry + h > WINDOW_HEIGHT:
            ry = ry - h - 5
        if ry < 0:
            ry = 0

        # 水平
        if rx + w > WINDOW_WIDTH:
            rx = WINDOW_WIDTH - w
        if rx < 0:
            rx = 0

        # 转回屏幕坐标
        self.menu_x = rx + win_l
        self.menu_y = ry + win_t

    def hide(self):
        self.active = False
        self.hover_index = -1

    def contains(self, sx, sy):
        """返回光标是否在菜单区域内（不改变任何状态）"""
        if not self.active:
            return False
        return (self.menu_x <= sx <= self.menu_x + self._menu_w and
                self.menu_y <= sy <= self.menu_y + self._menu_h)

    def move_grid(self, dx=0, dy=0):
        """按视觉网格移动键盘焦点。"""
        idx = self.selected_index
        if idx == 6:
            if dy < 0:
                idx = 4
            elif dy > 0:
                idx = 0
        else:
            row, col = divmod(idx, 2)
            if dx:
                col = 1 - col
            if dy < 0:
                idx = 6 if row == 0 else (row - 1) * 2 + col
            elif dy > 0:
                idx = 6 if row == 2 else (row + 1) * 2 + col
            else:
                idx = row * 2 + col
        self.selected_index = idx
        self.hover_index = -1

    def activate_selected(self):
        self.active = False
        return self.items[self.selected_index][1]

    def _index_at(self, sx, sy):
        for idx in range(len(self.items)):
            if self._item_rect(idx, screen_coords=True).collidepoint(sx, sy):
                return idx
        return None

    def _item_rect(self, idx, screen_coords=False):
        base_x = self.menu_x if screen_coords else 0
        base_y = self.menu_y if screen_coords else 0
        top = base_y + self.header_h + self.pad
        if idx < 6:
            row, col = divmod(idx, 2)
            return pygame.Rect(
                base_x + self.pad + col * (self.item_w + self.item_gap),
                top + row * (self.item_h + self.item_gap),
                self.item_w,
                self.item_h,
            )
        return pygame.Rect(
            base_x + self.pad,
            top + 3 * (self.item_h + self.item_gap),
            self.item_w * 2 + self.item_gap,
            self.quit_h,
        )

    def hit_test(self, sx, sy):
        if not self.active:
            return None
        w = self._menu_w
        h = self._menu_h
        if not (self.menu_x <= sx <= self.menu_x + w and
                self.menu_y <= sy <= self.menu_y + h):
            self.active = False
            return None
        idx = self._index_at(sx, sy)
        if idx is not None:
            self.active = False
            return self.items[idx][1]
        return None

    def update_hover(self, sx, sy):
        if not self.active:
            self.hover_index = -1
            return
        w = self._menu_w
        h = self._menu_h
        if not (self.menu_x <= sx <= self.menu_x + w and
                self.menu_y <= sy <= self.menu_y + h):
            self.hover_index = -1
            return
        idx = self._index_at(sx, sy)
        self.hover_index = idx if idx is not None else -1

    def draw(self, surf, win_l, win_t):
        if not self.active:
            return
        w = self._menu_w
        h = self._menu_h
        dx = self.menu_x - win_l
        dy = self.menu_y - win_t
        radius = 13

        shadow = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 75), (4, 4, w, h), border_radius=radius)
        surf.blit(shadow, (dx - 4, dy - 3))
        bg_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surface, (25, 27, 35, 246), bg_surface.get_rect(), border_radius=radius)
        pygame.draw.rect(bg_surface, (88, 95, 119, 170), bg_surface.get_rect(), 1, border_radius=radius)
        surf.blit(bg_surface, (dx, dy))

        if self.font is None:
            fonts = ('Microsoft YaHei UI', 'Microsoft YaHei', 'simsun')
            self.font = pygame.font.SysFont(fonts, 14, bold=True)
            self.hint_font = pygame.font.SysFont(fonts, 10)
            self.title_font = pygame.font.SysFont(fonts, 12, bold=True)

        title = self.title_font.render('和我互动', True, (245, 247, 255))
        surf.blit(title, (dx + self.pad + 5, dy + 10))
        key_hint = self.hint_font.render('方向键 · Enter', True, (125, 135, 165))
        surf.blit(key_hint, (dx + w - key_hint.get_width() - 12, dy + 12))
        pygame.draw.line(surf, (66, 71, 88),
                         (dx + 10, dy + self.header_h),
                         (dx + w - 10, dy + self.header_h))

        focus_index = (self.hover_index
                       if isinstance(self.hover_index, int) and self.hover_index >= 0
                       else self.selected_index)
        symbols = {
            'feed': '+', 'pet': '~', 'switch_book': 'A',
            'import_words': '^', 'set_interval': 'T',
            'delete_book': '-', 'quit': 'x',
        }
        for idx, (label, action, hint) in enumerate(self.items):
            rect = self._item_rect(idx).move(dx, dy)
            focused = idx == focus_index
            if action == 'quit':
                pygame.draw.line(surf, (66, 71, 88),
                                 (rect.left, rect.top - 3),
                                 (rect.right, rect.top - 3))
                if focused:
                    _blit_rounded(surf, (127, 51, 66, 160), rect, 8)
                quit_text = self.font.render(f"{symbols[action]}  保存并退出", True, (244, 164, 178))
                surf.blit(quit_text, quit_text.get_rect(center=rect.center))
                continue

            if focused:
                _blit_rounded(surf, (72, 98, 214, 215), rect, 9)
                # 左侧高亮条
                _blit_rounded(surf, (158, 182, 255, 235),
                              (rect.x + 5, rect.y + 10, 3, rect.h - 20), 2)
                label_color = hint_color = symbol_color = (255, 255, 255)
                badge_color = (255, 255, 255, 46)
            else:
                _blit_rounded(surf, (37, 40, 52, 215), rect, 9)
                _blit_rounded(surf, (64, 69, 86, 120), rect, 9, width=1)
                label_color = (238, 240, 248)
                hint_color = (136, 144, 168)
                symbol_color = (150, 162, 195)
                badge_color = (255, 255, 255, 18)
                if action == 'delete_book':
                    label_color = (242, 168, 180)
                    symbol_color = (242, 168, 180)

            # 图标徽章：圆角小方块居中放符号
            badge = pygame.Rect(rect.x + 9, rect.y + 10, 26, 26)
            _blit_rounded(surf, badge_color, badge, 7)
            symbol = self.title_font.render(symbols[action], True, symbol_color)
            surf.blit(symbol, symbol.get_rect(center=badge.center))
            txt = self.font.render(label, True, label_color)
            surf.blit(txt, (rect.x + 44, rect.y + 7))
            hint_txt = self.hint_font.render(hint, True, hint_color)
            surf.blit(hint_txt, (rect.x + 44, rect.y + 25))


# ════════════════════════════════════════════

def _do_import_words(pet, word_list):
    """打开文件对话框导入单词表"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        pet.add_feedback('❌', (255, 100, 100), 3)
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title='导入单词表',
        filetypes=[
            ('支持格式', '*.txt;*.csv;*.json'),
            ('文本文件', '*.txt'),
            ('CSV文件', '*.csv'),
            ('JSON文件', '*.json'),
            ('所有文件', '*.*'),
        ],
    )
    root.destroy()

    if not path:
        return

    # 用文件名（不含后缀）作为单词本名称
    book_name = os.path.splitext(os.path.basename(path))[0]
    success, msg = word_list.import_file(path, book_name)
    pet.word_bubble_active = False
    pet.word_timer = 0.0

    if success:
        # 首次导入后 3 秒弹出第一个单词
        pet.word_timer = pet.word_interval - 3
        pet.add_feedback(f'✅ {msg}', (100, 255, 100), 1)
    else:
        pet.add_feedback(f'❌ {msg}', (255, 100, 100), 1)


def _do_switch_book(word_list, pet):
    """弹出选择对话框切换或删除单词本"""
    books = word_list.list_books()
    if not books:
        pet.add_feedback('📚 无单词本', (200, 200, 200), 2)
        return

    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        return

    root = tk.Tk()
    root.title('选择/删除单词本')
    root.attributes('-topmost', True)
    root.resizable(False, False)

    current = word_list.get_active_book_name()
    tk.Label(root, text=f'当前: {current}', font=('', 11)).pack(pady=(10, 4))

    # 列表框
    frame = tk.Frame(root)
    listbox = tk.Listbox(frame, font=('', 12), width=28, height=min(10, len(books)))
    scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
    listbox.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=listbox.yview)

    for name in books:
        suffix = ' ◀ 当前' if name == current else ''
        listbox.insert(tk.END, f'{name}{suffix}')

    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    if len(books) > 10:
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    chosen = [None]

    def refresh_list():
        """刷新列表框"""
        listbox.delete(0, tk.END)
        nonlocal books
        books = word_list.list_books()
        cur = word_list.get_active_book_name()
        for name in books:
            suffix = ' ◀ 当前' if name == cur else ''
            listbox.insert(tk.END, f'{name}{suffix}')
        # 更新标题
        for widget in root.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(text=f'当前: {cur}')
                break

    def on_ok():
        sel = listbox.curselection()
        if sel:
            chosen[0] = books[sel[0]]
        root.destroy()

    def on_delete():
        sel = listbox.curselection()
        if not sel:
            return
        name = books[sel[0]]
        if not messagebox.askyesno('确认删除', f'确定要删除单词本「{name}」吗？\n\n该操作不可恢复！'):
            return
        success, msg = word_list.delete_book(name)
        if success:
            refresh_list()
            if not word_list.list_books():
                root.destroy()
                return
        messagebox.showinfo('提示', msg, parent=root)

    def on_double_click(ev):
        on_ok()

    listbox.bind('<Double-Button-1>', on_double_click)

    # 按钮
    btn_frame = tk.Frame(root)
    tk.Button(btn_frame, text='确定', command=on_ok, width=10).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text='删除', command=on_delete, width=10, fg='red').pack(side=tk.LEFT, padx=6)
    btn_frame.pack(pady=(4, 12))

    root.protocol('WM_DELETE_WINDOW', root.destroy)
    root.eval('tk::PlaceWindow . center')

    root.grab_set()
    root.wait_window()

    cur_after = word_list.get_active_book_name()
    if chosen[0] and chosen[0] != cur_after:
        word_list.switch_book(chosen[0])
        pet.word_bubble_active = False
        pet.word_timer = pet.word_interval
        pet.add_feedback(f'📚 {chosen[0]}', (100, 200, 255), 2)
        pet.add_particles((100, 200, 255), 6)
    elif not chosen[0]:
        pass  # 取消或删除后自动关闭
    elif chosen[0] == cur_after:
        pet.add_feedback(f'已经是「{cur_after}」', (200, 200, 200), 2)


def _do_delete_book(word_list, pet):
    """删除当前单词本"""
    name = word_list.get_active_book_name()
    books = word_list.list_books()
    if len(books) <= 1:
        pet.add_feedback('🗑 至少保留一个', (255, 200, 100), 2)
        return

    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    ok = messagebox.askokcancel('删除单词本', f'确定删除「{name}」吗？\n（共 {len(word_list.words)} 个词）')
    root.destroy()

    if ok:
        success, msg = word_list.delete_book(name)
        if success:
            pet.word_bubble_active = False
            pet.word_timer = pet.word_interval
            pet.add_feedback(f'🗑 {name}', (255, 180, 100), 2)
        else:
            pet.add_feedback(f'❌ {msg}', (255, 100, 100), 2)


def _do_set_interval(pet):
    """打开输入框设置单词间隔时间"""
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        pet.add_feedback('❌', (255, 100, 100), 3)
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        result = simpledialog.askinteger(
            '设置单词间隔',
            f'输入间隔秒数（当前: {pet.word_interval} 秒）:',
            initialvalue=pet.word_interval,
            minvalue=10,
            maxvalue=3600,
        )
    finally:
        root.destroy()

    if result is not None:
        pet.word_interval = result
        pet.save()  # 持久化
        pet.add_feedback(f'⏱ {result}秒', (100, 200, 255), 2)
        pet.add_particles((100, 200, 255), 6)


def _handle_menu_action(action, pet, word_list):
    """统一处理鼠标和键盘触发的菜单动作；返回是否继续运行。"""
    if action == 'feed':
        pet.on_feed()
    elif action == 'pet':
        pet.on_pet()
    elif action == 'import_words':
        _do_import_words(pet, word_list)
    elif action == 'set_interval':
        _do_set_interval(pet)
    elif action == 'switch_book':
        _do_switch_book(word_list, pet)
    elif action == 'delete_book':
        _do_delete_book(word_list, pet)
    elif action == 'quit':
        return False
    return True


def main():
    _install_crash_logger()

    # ——— 单实例锁：已有实例运行则退出 ———
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _ERROR_ALREADY_EXISTS = 183
    _mutex = _kernel32.CreateMutexW(None, False, 'DeskPet_SingleInstance')
    if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        sys.exit(0)

    pygame.init()
    screen = pygame.display.set_mode(
        (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.NOFRAME
    )
    pygame.display.set_caption('DeskPet')

    hwnd = _get_hwnd()
    _set_window_transparent(hwnd)
    character.load_gifs()

    pet = Pet()
    word_list = WordList()
    # 启动时展示一次状态面板，顺带露出快捷键提示
    pet.show_panel(4)
    # 启动时有单词则尽快弹出第一个词（避免等完整间隔）
    if word_list.has_words():
        pet.word_timer = max(pet.word_timer, pet.word_interval - 3)
    menu = ContextMenu()
    clock = pygame.time.Clock()

    _move_window(hwnd, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)
    _set_clickthrough(hwnd, True)
    ct_enabled = True
    prev_lbtn = False  # 上一帧左键状态（用于全局点击检测）
    cur_cursor = None  # 当前光标缓存，避免每帧重设

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0  # 秒
        cx, cy = _get_cursor_screen_pos()
        over_pet = pet.hit_test(cx, cy)
        kb_focus = _window_focused(hwnd)  # 键盘交互需要窗口持有焦点

        # 鼠标穿透切换（仅在需要改变时）
        need_ct = not (over_pet or pet.is_dragging or menu.active or pet.word_bubble_active)
        if need_ct != ct_enabled:
            _set_clickthrough(hwnd, need_ct)
            ct_enabled = need_ct

        # 全局左键检测：菜单打开时，点击屏幕任意位置（除菜单项外）关闭菜单
        if menu.active:
            cur_lbtn = _is_lbutton_pressed()
            if cur_lbtn and not prev_lbtn:
                # 新按下的左键，检查是否点在菜单外
                if not menu.contains(cx, cy):
                    menu.hide()
            prev_lbtn = cur_lbtn
        else:
            prev_lbtn = False

        pet.is_hovered = over_pet and not pet.is_dragging

        # 悬停时显示手型光标（仅在变化时切换）
        wanted = pygame.SYSTEM_CURSOR_HAND if pet.is_hovered else pygame.SYSTEM_CURSOR_ARROW
        if wanted != cur_cursor:
            pygame.mouse.set_cursor(wanted)
            cur_cursor = wanted

        # ── 键盘移动（方向键 / WASD，需窗口持有焦点）──
        if not menu.active and not pet.word_bubble_active and not pet.is_dragging:
            keys = pygame.key.get_pressed()
            kdx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
            kdy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
            if kdx or kdy:
                if kdx:
                    pet.direction = 1 if kdx > 0 else -1
                pet.x += kdx * KEY_MOVE_SPEED * dt
                pet.y += kdy * KEY_MOVE_SPEED * dt
                pet._clamp_position()
                pet.show_panel(0.8)  # 移动期间保持状态面板可见

        # ── 事件 ──
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if menu.active:
                    if ev.key == pygame.K_ESCAPE:
                        menu.hide()
                    elif ev.key == pygame.K_UP:
                        menu.move_grid(dy=-1)
                    elif ev.key == pygame.K_DOWN:
                        menu.move_grid(dy=1)
                    elif ev.key == pygame.K_LEFT:
                        menu.move_grid(dx=-1)
                    elif ev.key == pygame.K_RIGHT:
                        menu.move_grid(dx=1)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        running = _handle_menu_action(
                            menu.activate_selected(), pet, word_list)
                    continue
                if pet.word_bubble_active and ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                    pet.word_bubble_active = False
                    word_list.advance()
                    pet.word_timer = 0.0
                # 字母键永远是小写 keysym（Shift 不改变 ev.key），无 K_F/K_P 常量
                elif ev.key == pygame.K_f:
                    pet.on_feed()
                    pet.show_panel()
                elif ev.key == pygame.K_p:
                    pet.on_pet()
                    pet.show_panel()
                elif ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                    pet.on_click()
                    pet.show_panel()
                elif ev.key == pygame.K_ESCAPE:
                    running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if menu.active:
                    action = menu.hit_test(cx, cy)
                    if action:
                        running = _handle_menu_action(action, pet, word_list)
                    continue

                if ev.button == 1:
                    # 单词气泡激活时：点击气泡区域即可关闭
                    if pet.word_bubble_active and word_list.has_words():
                        progress = f'{word_list.index + 1}/{len(word_list.words)}'
                        bubble_rect = character.get_word_bubble_rect(
                            word_list.get_current(), progress)
                        win_l = pet.x - PET_CENTER_X
                        win_t = pet.y - PET_CENTER_Y
                        if bubble_rect.collidepoint(cx - win_l, cy - win_t):
                            pet.word_bubble_active = False
                            word_list.advance()
                            pet.word_timer = 0.0
                            continue  # 不触发拖动和开心

                    if over_pet:
                        # 分层穿透窗口点击不一定触发系统激活，显式抢焦点
                        _user32.SetForegroundWindow(hwnd)
                        pet.is_dragging = True
                        pet.drag_offset_x = cx - pet.x
                        pet.drag_offset_y = cy - pet.y
                        pet.on_click()

                elif ev.button == 3 and over_pet:
                    pet.on_right_click()
                    menu.show(cx, cy, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)

            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1 and pet.is_dragging:
                    pet.is_dragging = False

            elif ev.type == pygame.MOUSEMOTION:
                menu.update_hover(cx, cy)
                if pet.is_dragging:
                    pet.x = cx - pet.drag_offset_x
                    pet.y = cy - pet.drag_offset_y
                    pet._clamp_position()
                    _move_window(hwnd, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)

        # ── 更新 ──
        pet.update(frozen=menu.active, dt=dt)

        # 单词定时器
        if word_list.has_words() and not pet.word_bubble_active and not menu.active:
            pet.word_timer += dt
            if pet.word_timer >= pet.word_interval:
                pet.word_bubble_active = True
                pet.word_timer = 0.0

        # ── 窗口跟随 ──
        if not pet.is_dragging and not menu.active:
            _move_window(hwnd, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)

        # ── 绘制 ──
        screen.fill(TRANSPARENT_COLOR)
        character.draw_pet(screen, pet)
        character.draw_status(screen, pet)
        character.draw_feedback(screen, pet)

        # 悬停但未获得焦点时提示：键盘需要先点击激活
        if (pet.is_hovered and not kb_focus
                and not menu.active and not pet.word_bubble_active):
            character.draw_kb_hint(screen)

        if pet.word_bubble_active:
            progress = f'{word_list.index + 1}/{len(word_list.words)}'
            character.draw_word_bubble(screen, word_list.get_current(), progress)

        if menu.active:
            menu.draw(screen, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)

        pygame.display.flip()

    pet.save()
    word_list.save()
    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
