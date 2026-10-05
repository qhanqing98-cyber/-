"""菜单与系统对话框；返回动作，不负责运行主循环。"""
import os
import pygame
from config import WINDOW_WIDTH, WINDOW_HEIGHT
from ui_theme import gradient_rounded, translucent_rounded as _blit_rounded

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
            ('隐藏桌宠', 'toggle_visibility', '托盘可随时恢复'),
            ('安静模式', 'toggle_quiet', '暂停走动和提醒'),
            ('暂停30分钟', 'pause_30', '稍后继续学习'),
            ('恢复学习', 'resume_learning', '取消暂停和安静'),
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
        rows = (len(self.items) - 1 + 1) // 2
        return (self.header_h + self.pad * 2 + self.item_h * rows +
                self.item_gap * rows + self.quit_h)

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

    def reposition(self, win_l, win_t):
        """画布因跨屏或显示器变化而移动时，保持菜单完整可见。"""
        self.menu_x = max(win_l, min(win_l + WINDOW_WIDTH - self._menu_w, self.menu_x))
        self.menu_y = max(win_t, min(win_t + WINDOW_HEIGHT - self._menu_h, self.menu_y))

    def contains(self, sx, sy):
        """返回光标是否在菜单区域内（不改变任何状态）"""
        if not self.active:
            return False
        return (self.menu_x <= sx <= self.menu_x + self._menu_w and
                self.menu_y <= sy <= self.menu_y + self._menu_h)

    def move_grid(self, dx=0, dy=0):
        """按视觉网格移动键盘焦点。"""
        idx = self.selected_index
        quit_index = len(self.items) - 1
        rows = (quit_index + 1) // 2
        if idx == quit_index:
            if dy < 0:
                idx = (rows - 1) * 2
            elif dy > 0:
                idx = 0
        else:
            row, col = divmod(idx, 2)
            if dx:
                col = 1 - col
            if dy < 0:
                idx = quit_index if row == 0 else (row - 1) * 2 + col
            elif dy > 0:
                idx = quit_index if row == rows - 1 else (row + 1) * 2 + col
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
        quit_index = len(self.items) - 1
        rows = (quit_index + 1) // 2
        if idx < quit_index:
            row, col = divmod(idx, 2)
            return pygame.Rect(
                base_x + self.pad + col * (self.item_w + self.item_gap),
                top + row * (self.item_h + self.item_gap),
                self.item_w,
                self.item_h,
            )
        return pygame.Rect(
            base_x + self.pad,
            top + rows * (self.item_h + self.item_gap),
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

    def set_runtime_state(self, state):
        self.items[6] = ('隐藏桌宠' if state['visible'] else '显示桌宠',
                         'toggle_visibility', '托盘可随时恢复')
        self.items[7] = ('退出安静' if state['quiet'] else '安静模式',
                         'toggle_quiet', '暂停走动和提醒')

    def draw(self, surf, win_l, win_t):
        if not self.active:
            return
        w = self._menu_w
        h = self._menu_h
        dx = self.menu_x - win_l
        dy = self.menu_y - win_t
        radius = 13

        # 莫奈面板：象牙白→薰衣草渐变 + 柔光晕圈（代替深色投影与硬边框）
        gradient_rounded(surf, (dx, dy, w, h), radius,
                         (250, 247, 238, 242), (225, 211, 235, 242),
                         glow=(202, 172, 216, 60))

        if self.font is None:
            fonts = ('Microsoft YaHei UI', 'Microsoft YaHei', 'simsun')
            self.font = pygame.font.SysFont(fonts, 14, bold=True)
            self.hint_font = pygame.font.SysFont(fonts, 10)
            self.title_font = pygame.font.SysFont(fonts, 12, bold=True)

        title = self.title_font.render('和我互动', True, (74, 92, 124))
        surf.blit(title, (dx + self.pad + 5, dy + 10))
        key_hint = self.hint_font.render('方向键 · Enter', True, (150, 158, 184))
        surf.blit(key_hint, (dx + w - key_hint.get_width() - 12, dy + 12))
        pygame.draw.line(surf, (208, 198, 224),
                         (dx + 10, dy + self.header_h),
                         (dx + w - 10, dy + self.header_h))

        focus_index = (self.hover_index
                       if isinstance(self.hover_index, int) and self.hover_index >= 0
                       else self.selected_index)
        symbols = {
            'feed': '+', 'pet': '~', 'switch_book': 'A',
            'import_words': '^', 'set_interval': 'T',
            'delete_book': '-', 'quit': 'x',
            'toggle_visibility': 'H', 'toggle_quiet': 'Q',
            'pause_30': '||', 'resume_learning': '>',
        }
        for idx, (label, action, hint) in enumerate(self.items):
            rect = self._item_rect(idx).move(dx, dy)
            focused = idx == focus_index
            if action == 'quit':
                pygame.draw.line(surf, (208, 198, 224),
                                 (rect.left, rect.top - 3),
                                 (rect.right, rect.top - 3))
                if focused:
                    _blit_rounded(surf, (238, 158, 138, 115), rect, 8)
                quit_text = self.font.render(f"{symbols[action]}  保存并退出", True, (219, 116, 96))
                surf.blit(quit_text, quit_text.get_rect(center=rect.center))
                continue

            if focused:
                # 蔚蓝→薰衣草渐变高亮，左侧淡金光条
                gradient_rounded(surf, rect, 9,
                                 (92, 156, 222, 240), (176, 152, 224, 240))
                _blit_rounded(surf, (245, 217, 139, 240),
                              (rect.x + 5, rect.y + 10, 3, rect.h - 20), 2)
                label_color = hint_color = symbol_color = (252, 251, 246)
                badge_color = (255, 255, 255, 70)
            else:
                _blit_rounded(surf, (255, 255, 255, 95), rect, 9)
                label_color = (76, 88, 114)
                hint_color = (146, 156, 180)
                symbol_color = (110, 134, 178)
                badge_color = (120, 145, 190, 40)
                if action == 'delete_book':
                    label_color = (209, 110, 92)
                    symbol_color = (209, 110, 92)

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
    try:
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
    finally:
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
        if not word_list.switch_book(chosen[0]):
            pet.add_feedback('切换失败，请查看日志', (219, 116, 96), 1)
            return
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
    try:
        ok = messagebox.askokcancel('删除单词本', f'确定删除「{name}」吗？\n（共 {len(word_list.words)} 个词）')
    finally:
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
        pet.word_timer = 0.0
        if not pet.save():
            pet.add_feedback('设置已生效，保存失败', (219, 116, 96), 1)
            return
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


