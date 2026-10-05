# -*- coding: utf-8 -*-
# main.py — 桌宠主程序
# 启动: python main.py  或双击 run_pet.bat

import ctypes
from ctypes import wintypes
import os
import sys
import time

import pygame

from config import (WINDOW_WIDTH, WINDOW_HEIGHT, FPS, IDLE_FPS, HIDDEN_FPS,
                    AUTOSAVE_INTERVAL, KEY_MOVE_SPEED, PET_CENTER_X, PET_CENTER_Y,
                    get_data_path, prepare_data_directory)
from window import (_get_hwnd, _window_focused, _set_window_layered,
                    _set_clickthrough, _get_cursor_screen_pos,
                    _is_lbutton_pressed, _LayeredCanvas, _user32, set_window_visible)
from menus import ContextMenu, _handle_menu_action
from modes import RuntimeModes
from gestures import DragGesture
from tray import TrayIcon
from desktop import foreground_is_fullscreen, canvas_origin
from timing import ReminderTimer
from storage import log
from logging.handlers import RotatingFileHandler
import logging
from pet import Pet
from words import WordList
import character


def _install_crash_logger():
    """滚动日志限制磁盘占用，普通存档错误与未捕获异常都可追踪。"""
    log.setLevel(logging.INFO)
    if not log.handlers:
        try:
            os.makedirs(get_data_path(), exist_ok=True)
            handler = RotatingFileHandler(os.path.join(get_data_path(), 'crash.log'),
                                          maxBytes=1024 * 1024, backupCount=2,
                                          encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            log.addHandler(handler)
        except OSError:
            log.addHandler(logging.StreamHandler())
    def _hook(exc_type, exc, tb):
        log.critical('未捕获异常', exc_info=(exc_type, exc, tb))
    sys.excepthook = _hook


def _dispatch_action(action, pet, word_list, modes, gesture, tray_available=True):
    modes.refresh(now=time.time())
    if action == 'reset_reminder':
        pet.reminder_reset_pending = True
        return True
    if action == 'center':
        gesture.cancel(pet)
        pet.recenter(*_get_cursor_screen_pos())
        modes.show()
        return True
    if action == 'toggle_visibility' and not tray_available:
        pet.add_feedback('托盘不可用，暂不能隐藏', (219, 116, 96), 1)
        return True
    if modes.apply_action(action):
        if action in ('toggle_quiet', 'pause_30', 'pause_today', 'resume_learning'):
            pet.show_panel()
            pet.add_feedback(modes.status_text(), (96, 106, 132), 1)
        if modes.last_error:
            pet.add_feedback('设置保存失败，稍后重试', (219, 116, 96), 1)
        return True
    result = _handle_menu_action(action, pet, word_list)
    if action in ('switch_book', 'import_words', 'set_interval', 'delete_book'):
        pet.reminder_reset_pending = True
    return result


def _sync_modes(modes, pet, gesture, menu, hwnd, canvas, previous):
    state = modes.snapshot()
    if state['visible'] != previous['visible']:
        gesture.cancel(pet)
        menu.hide()
        set_window_visible(hwnd, state['visible'])
        if state['visible']:
            canvas.invalidate()
    if state['quiet'] and not previous['quiet']:
        gesture.cancel(pet)
        pet.settle()
    if state['learning_paused'] or state['learning_paused'] != previous['learning_paused']:
        # 收起卡片不推进词库；恢复后等待一个完整间隔。
        pet.word_bubble_active = False
        pet.word_timer = 0.0
    menu.set_runtime_state(state)
    return state

def main():
    _install_crash_logger()

    # ——— 单实例锁：已有实例运行则退出 ———
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _ERROR_ALREADY_EXISTS = 183
    _mutex = _kernel32.CreateMutexW(None, False, 'DeskPet_SingleInstance')
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if not _mutex:
        raise ctypes.WinError()
    if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(_mutex)
        return

    canvas = pet = word_list = tray = modes = None
    try:
        prepare_data_directory()
        pygame.init()
        pygame.display.set_mode(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.NOFRAME
        )
        pygame.display.set_caption('DeskPet')

        hwnd = _get_hwnd()
        _set_window_layered(hwnd)
        canvas = _LayeredCanvas(hwnd, WINDOW_WIDTH, WINDOW_HEIGHT)
        # 场景画在离屏 SRCALPHA 面上，alpha=0 即窗口透明处
        scene = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        if not character.load_gifs() or 'idle' not in character._sprite_cache:
            raise RuntimeError('缺少可用的 idle.gif，请检查 gifs 资源目录')

        pet = Pet()
        word_list = WordList()
        if pet.last_error or word_list.last_error:
            pet.add_feedback('数据读取异常，请查看日志', (219, 116, 96), 1)
        # 启动时展示一次状态面板，顺带露出快捷键提示
        pet.show_panel(4)
        # 启动时有单词则尽快弹出第一个词（避免等完整间隔）
        if word_list.has_words():
            pet.word_timer = max(pet.word_timer, pet.word_interval - 3)
        menu = ContextMenu()
        gesture = DragGesture()
        modes = RuntimeModes()
        try:
            tray = TrayIcon(character._sprite_cache['idle'][0])
            tray.set_state(modes.snapshot())
        except OSError:
            log.exception('托盘初始化失败，保持宠物可见')
            if tray is not None:
                tray.close()
                tray = None
            modes.recovery_available = False
            pet.add_feedback('托盘不可用，暂不能隐藏', (219, 116, 96), 1)
        previous_mode = {'visible': True, 'quiet': False, 'learning_paused': False}
        fullscreen_check_at = 0.0
        clock = pygame.time.Clock()
        reminder = ReminderTimer()
        render_key = None

        _set_clickthrough(hwnd, True)
        ct_enabled = True
        prev_lbtn = False  # 上一帧左键状态（用于全局点击检测）
        autosave_timer = 0.0
        cur_cursor = None  # 当前光标缓存，避免每帧重设

        feed_pressed = False
        running = True
        while running:
            active = gesture.pending or bool(pet.feedback_items) or not pet.animation_finished
            dt_ms = clock.tick((FPS if active else IDLE_FPS) if modes.visible else HIDDEN_FPS)
            dt = min(dt_ms / 1000.0, 0.1)  # 秒
            modes.refresh(now=time.time())
            if tray is not None:
                for action in tray.poll():
                    running = _dispatch_action(action, pet, word_list, modes, gesture, tray.available)
                    if not running:
                        break
                modes.recovery_available = tray.available
            if time.monotonic() >= fullscreen_check_at:
                fullscreen_check_at = time.monotonic() + 0.5
                modes.refresh(foreground_is_fullscreen((hwnd, tray.hwnd if tray else None)))
            previous_mode = _sync_modes(modes, pet, gesture, menu, hwnd, canvas, previous_mode)
            if tray is not None:
                tray.set_state(previous_mode)
            if not running:
                break
            cx, cy = _get_cursor_screen_pos()
            over_pet = pet.hit_test(cx, cy)
            kb_focus = _window_focused(hwnd)  # 键盘交互需要窗口持有焦点
            win_l, win_t = canvas_origin(pet.x, pet.y, WINDOW_WIDTH, WINDOW_HEIGHT, PET_CENTER_X, PET_CENTER_Y)
            center = round(pet.x) - win_l, round(pet.y) - win_t
            event_origin = win_l, win_t
            if menu.active:
                menu.reposition(win_l, win_t)

            # 鼠标穿透切换（仅在需要改变时）
            over_bubble = False
            feed_rect = character.get_feed_button_rect(pet, center) if not menu.active else None
            over_feed = bool(feed_rect and feed_rect.collidepoint(cx - win_l, cy - win_t))
            if pet.word_bubble_active and word_list.has_words():
                progress = f'{word_list.index + 1}/{len(word_list.words)}'
                rect = character.get_word_bubble_rect(word_list.get_current(), progress, center)
                over_bubble = rect.collidepoint(cx - win_l, cy - win_t)
            need_ct = not (over_pet or over_feed or feed_pressed or gesture.pending or menu.active or over_bubble)
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

            pet.is_hovered = (over_pet or over_feed) and not pet.is_dragging
            pet.feed_hovered = over_feed
            if pet.is_hovered:
                pet.show_panel(1.5)  # 从角色移动到按钮时保留入口
            if not modes.visible or menu.active or pet.word_bubble_active:
                feed_pressed = False

            # 悬停时显示手型光标（仅在变化时切换）
            wanted = pygame.SYSTEM_CURSOR_HAND if pet.is_hovered else pygame.SYSTEM_CURSOR_ARROW
            if wanted != cur_cursor:
                pygame.mouse.set_cursor(wanted)
                cur_cursor = wanted

            # ── 键盘移动（方向键 / WASD，需窗口持有焦点）──
            if modes.visible and kb_focus and not menu.active and not pet.word_bubble_active and not gesture.pending:
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
                elif not modes.visible:
                    continue
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
                            running = _dispatch_action(menu.activate_selected(), pet, word_list,
                                                       modes, gesture, modes.recovery_available)
                        continue
                    if pet.word_bubble_active and ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                        pet.word_bubble_active = False
                        if not word_list.advance():
                            pet.add_feedback('进度保存失败，稍后重试', (219, 116, 96), 1)
                        pet.word_timer = 0.0
                    # 字母键永远是小写 keysym（Shift 不改变 ev.key），无 K_F/K_P 常量
                    elif ev.key == pygame.K_f:
                        pet.on_feed()
                        pet.show_panel()
                    elif ev.key == pygame.K_p:
                        pet.on_pet()
                        pet.show_panel()
                    elif ev.key == pygame.K_h and not (getattr(ev, 'mod', 0) & (pygame.KMOD_CTRL | pygame.KMOD_ALT)):
                        running = _dispatch_action('toggle_visibility', pet, word_list, modes, gesture, modes.recovery_available)
                    elif ev.key == pygame.K_q:
                        running = _dispatch_action('toggle_quiet', pet, word_list, modes, gesture, modes.recovery_available)
                    elif ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                        pet.on_click()
                        pet.show_panel()
                    elif ev.key == pygame.K_ESCAPE:
                        gesture.cancel(pet)
                        feed_pressed = False
                        pet.panel_timer = 0.0
                        if pet.word_bubble_active:
                            pet.word_bubble_active = False
                            pet.word_timer = 0.0

                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    sx, sy = (event_origin[0] + ev.pos[0], event_origin[1] + ev.pos[1]) if hasattr(ev, 'pos') else (cx, cy)
                    if menu.active:
                        action = menu.hit_test(sx, sy)
                        if action:
                            running = _dispatch_action(action, pet, word_list, modes, gesture, modes.recovery_available)
                        continue

                    if ev.button == 1:
                        button = character.get_feed_button_rect(pet, center)
                        if button and button.collidepoint(sx - win_l, sy - win_t):
                            feed_pressed = True
                            continue
                        # 单词气泡激活时：点击气泡区域即可关闭
                        if pet.word_bubble_active and word_list.has_words():
                            progress = f'{word_list.index + 1}/{len(word_list.words)}'
                            bubble_rect = character.get_word_bubble_rect(
                                word_list.get_current(), progress, center)
                            if bubble_rect.collidepoint(sx - win_l, sy - win_t):
                                pet.word_bubble_active = False
                                _user32.SetForegroundWindow(hwnd)
                                if not word_list.advance():
                                    pet.add_feedback('进度保存失败，稍后重试', (219, 116, 96), 1)
                                pet.word_timer = 0.0
                                continue  # 不触发拖动和开心

                        if pet.hit_test(sx, sy):
                            # 分层穿透窗口点击不一定触发系统激活，显式抢焦点
                            _user32.SetForegroundWindow(hwnd)
                            gesture.press(pet, sx, sy)

                    elif ev.button == 3 and pet.hit_test(sx, sy):
                        gesture.cancel(pet)
                        _user32.SetForegroundWindow(hwnd)
                        pet.on_right_click()
                        menu.show(sx, sy, win_l, win_t)

                elif ev.type == pygame.MOUSEBUTTONUP:
                    if ev.button == 1:
                        sx, sy = (event_origin[0] + ev.pos[0], event_origin[1] + ev.pos[1]) if hasattr(ev, 'pos') else (cx, cy)
                        if feed_pressed:
                            feed_pressed = False
                            button = character.get_feed_button_rect(pet, center)
                            if not menu.active and button and button.collidepoint(sx - win_l, sy - win_t):
                                pet.on_feed()
                                pet.show_panel()
                            continue
                        gesture.release(pet, sx, sy)

                elif ev.type == pygame.MOUSEMOTION:
                    menu.update_hover(cx, cy)
                    sx, sy = (event_origin[0] + ev.pos[0], event_origin[1] + ev.pos[1]) if hasattr(ev, 'pos') else (cx, cy)
                    gesture.move(pet, sx, sy)

            if feed_pressed and not _is_lbutton_pressed():
                feed_pressed = False  # 在窗口外松开时也取消，避免残留按下状态
            if gesture.pending:
                gesture.move(pet, cx, cy)
                if not _is_lbutton_pressed():
                    gesture.release(pet, cx, cy)
            previous_mode = _sync_modes(modes, pet, gesture, menu, hwnd, canvas, previous_mode)
            if tray is not None:
                tray.set_state(previous_mode)

            # ── 更新 ──
            if modes.visible:
                pet.update(frozen=menu.active or modes.quiet or gesture.pending or pet.is_hovered or feed_pressed, dt=dt)

            # 单词定时器
            reminder.update(pet, word_list.has_words(), modes.learning_paused, menu.active)

            autosave_timer += dt_ms / 1000.0
            if autosave_timer >= AUTOSAVE_INTERVAL:
                autosave_timer = 0.0
                pet_ok = pet.save()
                words_ok = word_list.save()
                modes_ok = modes.save()
                if not pet_ok or not words_ok or not modes_ok:
                    pet.add_feedback('保存失败，稍后重试', (219, 116, 96), 1)

            if not modes.visible:
                continue

            win_l, win_t = canvas_origin(pet.x, pet.y, WINDOW_WIDTH, WINDOW_HEIGHT, PET_CENTER_X, PET_CENTER_Y)
            center = round(pet.x) - win_l, round(pet.y) - win_t
            if menu.active:
                menu.reposition(win_l, win_t)
            progress = f'{word_list.index + 1}/{len(word_list.words)}' if word_list.has_words() else ''
            mode_text = modes.status_text()
            key = character.scene_key(pet, word_list.get_current(), progress, menu, kb_focus, center, mode_text)
            if key == render_key:
                canvas.present(scene, win_l, win_t, content_changed=False)
                continue

            # ── 绘制到离屏场景，再上传为窗口像素（同时完成窗口跟随）──
            scene.fill((0, 0, 0, 0))
            character.draw_pet(scene, pet, center)
            character.draw_status(scene, pet, center, mode_text)
            character.draw_feedback(scene, pet, center)

            # 悬停但未获得焦点时提示：键盘需要先点击激活
            if (pet.is_hovered and not kb_focus
                    and not menu.active and not pet.word_bubble_active):
                character.draw_kb_hint(scene, center)

            if pet.word_bubble_active:
                progress = f'{word_list.index + 1}/{len(word_list.words)}'
                character.draw_word_bubble(scene, word_list.get_current(), progress, center)

            if menu.active:
                menu.draw(scene, win_l, win_t)

            canvas.present(scene, win_l, win_t)
            render_key = key

    finally:
        # 各项清理互不阻断，确保绘图资源和 pygame 都会释放。
        for obj in (pet, word_list, modes):
            if obj is not None:
                try:
                    obj.save()
                except Exception:
                    log.exception('退出保存失败')
        try:
            if tray is not None:
                tray.close()
        finally:
            try:
                if canvas is not None:
                    canvas.close()
            finally:
                pygame.quit()
                _kernel32.CloseHandle(_mutex)


if __name__ == '__main__':
    main()
