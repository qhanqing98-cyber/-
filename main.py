# -*- coding: utf-8 -*-
# main.py — 桌宠主程序
# 启动: python main.py  或双击 run_pet.bat

import ctypes
from ctypes import wintypes
import os
import sys

import pygame

from config import *
from pet import Pet
from words import WordList
import character

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


# ─── 右键菜单 ────────────────────────────────

class ContextMenu:
    def __init__(self):
        self.active = False
        self.menu_x = 0
        self.menu_y = 0
        self.item_h = 32
        self.item_w = 140
        self.pad = 8
        self.scrollbar_w = 14  # 加宽，容纳 ▲/▼ 按钮
        self.max_visible = 4  # 超过 4 项可滚动
        self.scroll_offset = 0
        self.selected_index = 0
        self.items = [
            ('📖 导入单词表', 'import_words'),
            ('📚 选择单词本', 'switch_book'),
            ('🗑 删除单词本', 'delete_book'),
            ('⏱ 单词间隔', 'set_interval'),
            ('🍜 Feed', 'feed'),
            ('❤️ Pet', 'pet'),
            ('❌ Quit', 'quit'),
        ]
        self.font = None
        self.hover_index = -1
        self._scroll_btn_up = None   # 屏幕坐标 rect (▲)
        self._scroll_btn_down = None # 屏幕坐标 rect (▼)

    @property
    def _visible_count(self):
        """可用窗口高度内能完整显示的项数"""
        # 先从总项数限制
        n = min(len(self.items), self.max_visible)
        # 再从窗口高度限制（菜单要能完全显示）
        max_h = WINDOW_HEIGHT - self.pad * 2
        max_by_height = max(1, max_h // self.item_h)
        return min(n, max_by_height)

    @property
    def _menu_w(self):
        return self.item_w + self.pad * 2 + self.scrollbar_w

    @property
    def _menu_h(self):
        return self._visible_count * self.item_h + self.pad * 2

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

    def contains(self, sx, sy):
        """返回光标是否在菜单区域内（不改变任何状态）"""
        if not self.active:
            return False
        return (self.menu_x <= sx <= self.menu_x + self._menu_w and
                self.menu_y <= sy <= self.menu_y + self._menu_h)

    def scroll(self, delta):
        """滚轮：delta>0 上滚，delta<0 下滚"""
        total = len(self.items)
        if total <= self.max_visible:
            return
        max_offset = total - self.max_visible
        self.scroll_offset = max(0, min(self.scroll_offset - delta, max_offset))
        # 同时让选中项保持在可见范围内
        if self.selected_index < self.scroll_offset:
            self.selected_index = self.scroll_offset
        elif self.selected_index >= self.scroll_offset + self.max_visible:
            self.selected_index = self.scroll_offset + self.max_visible - 1

    def hit_test(self, sx, sy):
        if not self.active:
            return None
        w = self._menu_w
        h = self._menu_h
        if not (self.menu_x <= sx <= self.menu_x + w and
                self.menu_y <= sy <= self.menu_y + h):
            self.active = False
            return None
        rel_idx = (sy - self.menu_y - self.pad) // self.item_h
        idx = self.scroll_offset + rel_idx
        if 0 <= idx < len(self.items) and rel_idx < self._visible_count:
            self.active = False
            return self.items[idx][1]
        self.active = False
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
        rel_idx = (sy - self.menu_y - self.pad) // self.item_h
        idx = self.scroll_offset + rel_idx
        if 0 <= idx < len(self.items) and rel_idx < self._visible_count:
            self.hover_index = idx
        else:
            self.hover_index = -1

    def _draw_rounded_rect(self, surf, color, rect, radius):
        x, y, w, h = rect
        pygame.draw.rect(surf, color, (x + radius, y, w - radius * 2, h))
        pygame.draw.rect(surf, color, (x, y + radius, w, h - radius * 2))
        pygame.draw.circle(surf, color, (x + radius, y + radius), radius)
        pygame.draw.circle(surf, color, (x + w - radius, y + radius), radius)
        pygame.draw.circle(surf, color, (x + radius, y + h - radius), radius)
        pygame.draw.circle(surf, color, (x + w - radius, y + h - radius), radius)

    def draw(self, surf, win_l, win_t):
        if not self.active:
            return
        w = self._menu_w
        h = self._menu_h
        dx = self.menu_x - win_l
        dy = self.menu_y - win_t
        radius = 8

        bg_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        self._draw_rounded_rect(bg_surface, (30, 30, 35, 240), (0, 0, w, h), radius)
        pygame.draw.rect(bg_surface, (60, 60, 70, 200), (0, 0, w, h), 1, radius)
        surf.blit(bg_surface, (dx, dy))

        if self.font is None:
            self.font = pygame.font.SysFont('simsun', 14)

        total = len(self.items)
        for i_rel in range(self._visible_count):
            i_abs = self.scroll_offset + i_rel
            if i_abs >= total:
                break
            label, _ = self.items[i_abs]
            iy = dy + self.pad + i_rel * self.item_h
            ix = dx + self.pad

            if i_abs == self.hover_index:
                item_bg = pygame.Surface((self.item_w, self.item_h - 2), pygame.SRCALPHA)
                self._draw_rounded_rect(item_bg, (60, 120, 200, 150), (0, 0, self.item_w, self.item_h - 2), 4)
                surf.blit(item_bg, (ix, iy))
                text_color = (255, 255, 255)
            elif i_abs == total - 1 and 'Quit' in label:
                item_bg = pygame.Surface((self.item_w, self.item_h - 2), pygame.SRCALPHA)
                self._draw_rounded_rect(item_bg, (200, 60, 80, 100), (0, 0, self.item_w, self.item_h - 2), 4)
                surf.blit(item_bg, (ix, iy))
                text_color = (240, 200, 200)
            else:
                text_color = (230, 230, 230)

            txt = self.font.render(label, True, text_color)
            surf.blit(txt, (ix + 6, iy + 6))

        if total > self.max_visible:
            sb_x = dx + w - self.scrollbar_w - 4
            sb_y = dy + 4
            sb_h = h - 8
            # 背景槽
            pygame.draw.rect(surf, (50, 50, 55), (sb_x, sb_y, self.scrollbar_w, sb_h), 0, 2)
            # ▲ 上滚按钮
            btn_h = 12
            self._scroll_btn_up = (self.menu_x + sb_x - dx, self.menu_y + sb_y - dy, self.scrollbar_w, btn_h)
            pygame.draw.rect(surf, (80, 80, 90), self._scroll_btn_up, 0, 2)
            up_font = pygame.font.SysFont('simsun', 10)
            up_txt = up_font.render('▲', True, (200, 200, 200))
            surf.blit(up_txt, (sb_x + 2, sb_y + 1))
            # ▼ 下滚按钮
            self._scroll_btn_down = (self.menu_x + sb_x - dx, self.menu_y + sb_y + sb_h - btn_h - dy, self.scrollbar_w, btn_h)
            pygame.draw.rect(surf, (80, 80, 90), self._scroll_btn_down, 0, 2)
            dn_txt = up_font.render('▼', True, (200, 200, 200))
            surf.blit(dn_txt, (sb_x + 2, sb_y + sb_h - btn_h + 1))
            # 滑块
            thumb_track_h = sb_h - btn_h * 2
            thumb_h = max(12, thumb_track_h * self.max_visible // total)
            thumb_y = sb_y + btn_h + (thumb_track_h - thumb_h) * self.scroll_offset // (total - self.max_visible)
            thumb_surface = pygame.Surface((self.scrollbar_w, thumb_h), pygame.SRCALPHA)
            self._draw_rounded_rect(thumb_surface, (100, 100, 110), (0, 0, self.scrollbar_w, thumb_h), 2)
            surf.blit(thumb_surface, (sb_x, thumb_y))


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
        pet.word_timer = WORD_INTERVAL - 3
        pet.add_feedback(f'✅ {msg}', (100, 255, 100), 1)
    else:
        pet.add_feedback(f'❌ {msg}', (255, 100, 100), 1)


def _do_switch_book(word_list, pet):
    """弹出选择对话框切换单词本"""
    books = word_list.list_books()
    if not books:
        pet.add_feedback('📚 无单词本', (200, 200, 200), 2)
        return

    try:
        import tkinter as tk
    except ImportError:
        return

    root = tk.Tk()
    root.title('选择单词本')
    root.attributes('-topmost', True)
    root.geometry(f'300x{min(400, len(books)*40 + 60)}')

    current = word_list.get_active_book_name()
    tk.Label(root, text=f'当前: {current}', font=('', 11)).pack(pady=8)

    listbox = tk.Listbox(root, font=('', 12), height=min(10, len(books)))
    for name in books:
        suffix = ' ◀ 当前' if name == current else ''
        listbox.insert(tk.END, f'{name}{suffix}')
    listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    chosen = [None]

    def on_ok():
        sel = listbox.curselection()
        if sel:
            chosen[0] = books[sel[0]]
        root.destroy()

    def on_double_click(ev):
        on_ok()

    listbox.bind('<Double-Button-1>', on_double_click)
    tk.Button(root, text='确定', command=on_ok, width=10).pack(pady=8)
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    root.eval('tk::PlaceWindow . center')

    root.grab_set()
    root.wait_window()

    if chosen[0] and chosen[0] != current:
        word_list.switch_book(chosen[0])
        # 重置气泡定时器，立即显示新本的第一个词
        pet.word_bubble_active = False
        pet.word_timer = WORD_INTERVAL  # 让气泡马上弹出
        pet.add_feedback(f'📚 {chosen[0]}', (100, 200, 255), 2)
        pet.add_particles((100, 200, 255), 6)
    elif not chosen[0]:
        pass  # 取消
    else:
        pet.add_feedback(f'已经是「{current}」', (200, 200, 200), 2)


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
            pet.word_timer = WORD_INTERVAL
            pet.add_feedback(f'🗑 {name}', (255, 180, 100), 2)
        else:
            pet.add_feedback(f'❌ {msg}', (255, 100, 100), 2)


def _do_set_interval(pet):
    """打开输入框设置单词间隔时间"""
    global WORD_INTERVAL
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
            f'输入间隔秒数（当前: {WORD_INTERVAL} 秒）:',
            initialvalue=WORD_INTERVAL,
            minvalue=10,
            maxvalue=3600,
        )
    finally:
        root.destroy()

    if result is not None:
        WORD_INTERVAL = result
        pet.word_interval = result
        pet.save()  # 持久化
        pet.add_feedback(f'⏱ {result}秒', (100, 200, 255), 2)
        pet.add_particles((100, 200, 255), 6)


def main():
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
    global WORD_INTERVAL
    WORD_INTERVAL = pet.word_interval  # 使用持久化的间隔值
    word_list = WordList()
    menu = ContextMenu()
    clock = pygame.time.Clock()

    _move_window(hwnd, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)
    _set_clickthrough(hwnd, True)
    ct_enabled = True
    prev_lbtn = False  # 上一帧左键状态（用于全局点击检测）

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0  # 秒
        cx, cy = _get_cursor_screen_pos()
        over_pet = pet.hit_test(cx, cy)

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

        # 悬停时显示手型光标
        if pet.is_hovered:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        # ── 事件 ──
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False

            elif ev.type == pygame.MOUSEWHEEL:
                if menu.active:
                    menu.scroll(ev.y)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if menu.active:
                    if ev.button == 4:    # 滚轮上滑
                        menu.scroll(1)
                        continue
                    elif ev.button == 5:  # 滚轮下滑
                        menu.scroll(-1)
                        continue
                    # 检查是否点击了 ▲/▼ 滚动按钮
                    if menu._scroll_btn_up and menu._scroll_btn_down:
                        ux, uy, uw, uh = menu._scroll_btn_up
                        dx_, dy_, dw_, dh_ = menu._scroll_btn_down
                        if ux <= cx <= ux + uw and uy <= cy <= uy + uh:
                            menu.scroll(1)
                            continue
                        if dx_ <= cx <= dx_ + dw_ and dy_ <= cy <= dy_ + dh_:
                            menu.scroll(-1)
                            continue
                    action = menu.hit_test(cx, cy)
                    if action == 'feed':
                        pet.on_feed()
                    elif action == 'pet':
                        pet.on_pet()
                    elif action == 'quit':
                        running = False
                    elif action == 'import_words':
                        menu.active = False
                        _do_import_words(pet, word_list)
                    elif action == 'set_interval':
                        menu.active = False
                        _do_set_interval(pet)
                    elif action == 'switch_book':
                        menu.active = False
                        _do_switch_book(word_list, pet)
                    elif action == 'delete_book':
                        menu.active = False
                        _do_delete_book(word_list, pet)
                    continue

                if ev.button == 1:
                    # 单词气泡激活时：点击气泡区域即可关闭
                    if pet.word_bubble_active and word_list.has_words():
                        # 气泡大致在宠物上方 30~230px 范围内
                        bubble_cx = pet.x
                        bubble_cy_top = pet.y - 230
                        bubble_cy_bot = pet.y - 30
                        if (abs(cx - bubble_cx) < 150 and
                            bubble_cy_top <= cy <= bubble_cy_bot):
                            pet.word_bubble_active = False
                            word_list.advance()
                            pet.word_timer = 0.0
                            continue  # 不触发拖动和开心

                    if over_pet:
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
            if pet.word_timer >= WORD_INTERVAL:
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

        if pet.word_bubble_active:
            character.draw_word_bubble(screen, word_list.get_current())

        if menu.active:
            menu.draw(screen, pet.x - PET_CENTER_X, pet.y - PET_CENTER_Y)

        pygame.display.flip()

    pet.save()
    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
