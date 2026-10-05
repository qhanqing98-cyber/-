# character.py — GIF 桌宠绘制

import os
import math
from bisect import bisect_right
from functools import lru_cache
from collections import OrderedDict
from collections.abc import Sequence
import operator

import pygame

from config import (WINDOW_WIDTH, WINDOW_HEIGHT, PET_CENTER_X, PET_CENTER_Y,
                    B_IDLE, B_WALK, B_SLEEP, B_HAPPY, B_SAD, B_SURPRISED,
                    B_PETTING, B_LIFT, FEED_HUNGER_BOOST,
                    get_resource_path)
from ui_theme import gradient_rounded, translucent_rounded

# ─── 精灵图缓存 ──────────────────────────────
_sprite_cache = {}
_flipped_cache = {}
_use_sprites = False
_font_cache = {}
_frame_end_times = {}
_DERIVED_LIMIT = 8 * 1024 * 1024
_derived_frames = OrderedDict()
_derived_bytes = 0


class _LazyFrames(Sequence):
    """像列表一样取帧；只生成正在使用的帧，派生画面共享 8 MiB 上限。"""
    def __init__(self, count, key, factory):
        self.count, self.key, self.factory = count, key, factory

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        global _derived_bytes
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.count))]
        index = operator.index(index)
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        key = self.key, index
        if key in _derived_frames:
            _derived_frames.move_to_end(key)
            return _derived_frames[key]
        frame = self.factory(index)
        size = frame.get_pitch() * frame.get_height()
        while _derived_frames and _derived_bytes + size > _DERIVED_LIMIT:
            _, old = _derived_frames.popitem(last=False)
            _derived_bytes -= old.get_pitch() * old.get_height()
        if size <= _DERIVED_LIMIT:
            _derived_frames[key] = frame
            _derived_bytes += size
        return frame


def animation_memory_bytes():
    """统计实际持有的像素缓存，不触发延迟帧生成。"""
    base = sum(frame.get_pitch() * frame.get_height()
               for frames in _sprite_cache.values() if not isinstance(frames, _LazyFrames)
               for frame in frames)
    return base + _derived_bytes



def _font(size, bold=False):
    """统一 UI 字体并缓存，避免每帧反复创建字体对象。"""
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(
            ('Microsoft YaHei UI', 'Microsoft YaHei', 'simsun'),
            size,
            bold=bold,
        )
    return _font_cache[key]


# ════════════════════════════════════════════
# GIF 动画加载（gifs/ 目录，一个 .gif 对应一个行为）
# ════════════════════════════════════════════


def load_gifs(gif_dir='gifs'):
    """从 gifs/ 目录加载 GIF 作为精灵图动画。

    命名规则：walk.gif → 动画名 'walk'，所有帧作为该动画帧序列。
    若 gifs/ 存在且有 .gif 文件，则加载并启用精灵模式。
    """
    global _sprite_cache, _flipped_cache, _use_sprites
    gifs_path = os.path.join(get_resource_path(), gif_dir)
    if not os.path.isdir(gifs_path):
        return False

    gif_files = [f for f in os.listdir(gifs_path)
                 if f.lower().endswith('.gif')]
    if not gif_files:
        return False

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return False

    global _derived_bytes
    _derived_frames.clear()
    _derived_bytes = 0
    _sprite_cache.clear()
    _flipped_cache.clear()
    _frame_end_times.clear()
    _font_cache.clear()
    _cached_word_bubble_layout.cache_clear()
    _use_sprites = False

    loaded_any = False
    for fname in sorted(gif_files):
        anim_name = os.path.splitext(fname)[0]  # 'walk' from 'walk.gif'
        path = os.path.join(gifs_path, fname)
        pil_gif = None
        try:
            pil_gif = Image.open(path)
            frames = []
            frame_end_times = []
            elapsed = 0.0
            n_frames = getattr(pil_gif, 'n_frames', 1)
            trans_idx = pil_gif.info.get('transparency', -1)

            for i in range(n_frames):
                pil_gif.seek(i)
                elapsed += max(10, pil_gif.info.get('duration', 100)) / 1000.0
                frame_end_times.append(elapsed)
                frame = pil_gif.copy()

                # Palette → RGBA（正确处理透明色）
                if frame.mode == 'P':
                    palette = frame.getpalette()
                    palette_arr = np.array(palette, dtype=np.uint8).reshape(-1, 3)
                    idx_arr = np.array(frame, dtype=np.uint8)

                    rgb_arr = palette_arr[idx_arr]  # (H, W, 3)

                    if trans_idx >= 0:
                        alpha = np.where(idx_arr == trans_idx, 0, 255).astype(np.uint8)
                    else:
                        alpha = np.full((frame.height, frame.width), 255, dtype=np.uint8)

                    rgba_arr = np.concatenate([rgb_arr, alpha[:, :, np.newaxis]], axis=2)
                    pil_frame = Image.fromarray(rgba_arr)
                else:
                    pil_frame = frame.convert('RGBA')

                # 缩放到合适大小（限制高度 200px 以内，保持比例）
                target_h = 200
                w, h = pil_frame.size
                if h > target_h:
                    scale = target_h / h
                    new_w = max(1, int(w * scale))
                    pil_frame = pil_frame.resize((new_w, target_h), Image.LANCZOS)

                # 保留真实 alpha：每像素 alpha 分层窗口直接使用 alpha
                # 通道，半透明边缘平滑，不再需要品红键控。
                data = pil_frame.tobytes()
                surf = pygame.image.fromstring(data, pil_frame.size, 'RGBA')
                # 翻转使角色默认朝右（GIF 源默认朝左）
                surf = pygame.transform.flip(surf, True, False)
                frames.append(surf)

            if frames:
                _frame_end_times[anim_name] = frame_end_times
                groups = {anim_name: frames}
                _sprite_cache.update(groups)
                for an, f_list in groups.items():
                    _flipped_cache[an] = _LazyFrames(len(f_list), ('flip', id(f_list)),
                                                   lambda i, source=f_list: pygame.transform.flip(source[i], True, False))
                loaded_any = True
                print(f'  [GIF] {fname}: {n_frames} frames, {frames[0].get_width()}x{frames[0].get_height()}')

        except Exception as e:
            print(f'  [GIF] Failed to load {fname}: {e}')
        finally:
            if pil_gif is not None:
                pil_gif.close()

    if loaded_any:
        _build_interaction_animations()
        _use_sprites = True
        return True
    return False


def _draw_heart(surface, center, size, color):
    x, y = center
    radius = max(2, size // 3)
    pygame.draw.circle(surface, color, (int(x - radius), int(y - radius)), radius)
    pygame.draw.circle(surface, color, (int(x + radius), int(y - radius)), radius)
    pygame.draw.polygon(surface, color, [(x - radius * 2, y - radius),
                                        (x + radius * 2, y - radius), (x, y + radius * 2)])


def _draw_hand(surface, x, y):
    """莫奈色的小手，随摸头动作沿头顶往返。"""
    pygame.draw.rect(surface, (235, 201, 176), (int(x) - 17, int(y) - 5, 34, 12), border_radius=6)
    pygame.draw.rect(surface, (250, 247, 238), (int(x) + 13, int(y) - 7, 10, 16), border_radius=3)
    for offset in (-12, -5, 2):
        pygame.draw.line(surface, (202, 169, 147), (int(x) + offset, int(y) + 1),
                         (int(x) + offset + 9, int(y) + 1), 1)


def _interaction_frame(name, original, index, count):
    """从同一张角色原图绘制当前动作帧；画面由有上限的缓存复用。"""
    width, height = original.get_size()
    size = width + 80, height + 80
    center = size[0] // 2, size[1] // 2
    t = index / count
    image = original
    x, y = center
    frame = pygame.Surface(size, pygame.SRCALPHA)
    if name == B_HAPPY:
        if t < 0.7:
            y -= round(24 * math.sin(math.pi * t / 0.7))
        else:
            squash = 0.07 * math.sin(math.pi * (t - 0.7) / 0.3)
            image = pygame.transform.smoothscale(original, (round(width * (1 + squash)),
                                                             round(height * (1 - squash))))
            y += (height - image.get_height()) // 2
    elif name == B_PETTING:
        y += round(2 * math.sin(t * math.tau * 2))
    elif name == B_LIFT:
        image = pygame.transform.rotozoom(original, 7 * math.sin(t * math.tau), 1.0)
        y -= 8
    else:
        image = pygame.transform.rotozoom(original, -3, 1.0)
        y += round(3 + 2 * math.sin(t * math.tau))
    frame.blit(image, image.get_rect(center=(x, y)))
    head_y = center[1] - height // 2 + 7
    if name == B_HAPPY and 0.12 < t < 0.85:
        _draw_heart(frame, (center[0] + width // 2 - 4, head_y + 6 - int(t * 15)),
                    12, (232, 144, 122, 240))
    elif name == B_PETTING:
        _draw_hand(frame, center[0] + math.sin(t * math.tau * 2) * 17, head_y)
        _draw_heart(frame, (center[0] - width // 2, head_y + 20), 9, (232, 144, 122, 225))
    elif name == B_LIFT:
        _draw_hand(frame, center[0], head_y - 8)
    return frame


def _build_interaction_animations():
    """登记延迟互动序列；用户提供同名 GIF 时优先使用 GIF。"""
    idle = _sprite_cache.get(B_IDLE)
    if not idle:
        return
    original = idle[0]
    for name, count, rate in ((B_HAPPY, 30, 30), (B_PETTING, 36, 30),
                              (B_LIFT, 36, 30), (B_SAD, 24, 12)):
        if name in _sprite_cache:
            continue
        frames = _LazyFrames(count, ('interaction', name, id(original)),
                             lambda i, name=name, count=count: _interaction_frame(name, original, i, count))
        _sprite_cache[name] = frames
        _flipped_cache[name] = _LazyFrames(count, ('flip', id(frames)),
                                          lambda i, source=frames: pygame.transform.flip(source[i], True, False))
        _frame_end_times[name] = [(i + 1) / rate for i in range(count)]


# ════════════════════════════════════════════
# 主绘制入口
# ════════════════════════════════════════════

def draw_pet(surface, pet, center=None):
    """绘制宠物（GIF 精灵图）"""
    _draw_sprite(surface, pet, center)


def scene_key(pet, word_data, progress, menu, kb_focus, center, mode_text):
    """只记录会改变可见像素的状态，位置变化交给窗口移动处理。"""
    anim = pet.get_anim_name()
    if anim not in _sprite_cache:
        anim = B_IDLE
    frame = animation_frame_index(anim, pet.animation_elapsed)
    panel = not pet.word_bubble_active and (pet.is_hovered or pet.panel_timer > 0)
    status = None
    if panel:
        status = (pet.behavior, mode_text, getattr(pet, 'feed_hovered', False),
                  tuple((f'{v:.0f}', int(88 * v / 100)) for v in (pet.hunger, pet.mood, pet.energy)))
    feedback = tuple(tuple(sorted(item.items())) for item in pet.feedback_items)
    hint = pet.is_hovered and not kb_focus and not menu.active and not pet.word_bubble_active
    bubble = (word_data['word'], word_data.get('meaning', ''), progress) if pet.word_bubble_active and word_data else None
    menu_state = (menu.selected_index, menu.hover_index, tuple(menu.items), menu.menu_x - round(pet.x) + center[0],
                  menu.menu_y - round(pet.y) + center[1]) if menu.active else None
    return anim, frame, pet.direction, center, status, feedback, hint, bubble, menu_state


def animation_frame_index(anim, elapsed):
    """累计时间落在哪一帧；绘制多少次都不会改变动画状态。"""
    ends = _frame_end_times.get(anim)
    if not ends:
        return 0
    return min(len(ends) - 1, bisect_right(ends, (elapsed + 1e-9) % ends[-1]))


def _draw_sprite(surface, pet, center=None):
    anim = pet.get_anim_name()

    frames = _sprite_cache.get(anim)
    if not frames:
        frames = _sprite_cache.get(B_IDLE)
        anim = B_IDLE
    if not frames:
        return

    idx = animation_frame_index(anim, pet.animation_elapsed)

    if pet.direction < 0:
        flipped_frames = _flipped_cache.get(anim)
        if flipped_frames:
            img = flipped_frames[idx]
        else:
            img = frames[idx]
    else:
        img = frames[idx]

    rect = img.get_rect(center=center or (PET_CENTER_X, PET_CENTER_Y))
    surface.blit(img, rect)


def draw_feedback(surface, pet, center=None):
    """绘制互动反馈（粒子和浮动文字）"""
    if not pet.feedback_items:
        return
    font = _font(16, bold=True)
    cx, cy = center or (PET_CENTER_X, PET_CENTER_Y)
    dx, dy = cx - PET_CENTER_X, cy - PET_CENTER_Y
    for item in pet.feedback_items:
        alpha = int(item['alpha'] * 255)
        if item['type'] == 'text':
            r, g, b = item['color']
            txt = font.render(item['text'], True, (r, g, b, alpha))
            txt.set_alpha(alpha)
            surface.blit(txt, (item['x'] + dx, item['y'] + dy))
        elif item['type'] == 'particle':
            r, g, b = item['color']
            s = pygame.Surface((item['size'] * 2, item['size'] * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (r, g, b, alpha), (item['size'], item['size']), item['size'])
            surface.blit(s, (item['x'] + dx - item['size'], item['y'] + dy - item['size']))


# ════════════════════════════════════════════
# 悬停状态面板
# ════════════════════════════════════════════

def draw_kb_hint(surface, center=None):
    """悬停但窗口无键盘焦点时的提示气泡（象牙白胶囊 + 薰衣草描边）。"""
    txt = _font(11).render('点击桌宠启用键盘操作', True, (96, 110, 140))
    pad = 9
    w = txt.get_width() + pad * 2
    h = 24
    cx, cy = center or (PET_CENTER_X, PET_CENTER_Y)
    x = max(8, min(surface.get_width() - w - 8, cx - w // 2))
    y = max(8, min(surface.get_height() - h - 8, cy - 140))
    pill = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(pill, (250, 247, 238, 228), pill.get_rect(), border_radius=12)
    pygame.draw.rect(pill, (200, 168, 212, 180), pill.get_rect(), 1, border_radius=12)
    pill.blit(txt, (pad, (h - txt.get_height()) // 2))
    surface.blit(pill, (x, y))


def _status_rect(center=None):
    cx, cy = center or (PET_CENTER_X, PET_CENTER_Y)
    px = cx + 42
    if px + 172 + 8 > WINDOW_WIDTH:
        px = cx - 172 - 42
    px = max(8, min(WINDOW_WIDTH - 172 - 8, px))
    py = cy - 136 - 54
    if py < 8:
        py = cy + 112
    return pygame.Rect(px, max(8, min(WINDOW_HEIGHT - 136 - 8, py)), 172, 136)


def get_feed_button_rect(pet, center=None):
    """绘制与点击共用同一按钮区域；面板隐藏或卡片出现时不可点击。"""
    if pet.word_bubble_active or not (pet.is_hovered or pet.panel_timer > 0):
        return None
    panel = _status_rect(center)
    return pygame.Rect(panel.x + 12, panel.bottom - 27, panel.width - 24, 22)


def draw_status(surface, pet, center=None, mode_text='学习开启'):
    if pet.word_bubble_active:
        return
    # 鼠标悬停或键盘交互（panel_timer 未到期）时显示
    if not pet.is_hovered and getattr(pet, 'panel_timer', 0.0) <= 0:
        return

    font = _font(12)
    # 莫奈粉彩：淡金 / 珊瑚 / 蔚蓝
    lines = [
        ('饱食', pet.hunger, (191, 146, 54)),
        ('心情', pet.mood, (214, 110, 95)),
        ('精力', pet.energy, (64, 120, 190)),
    ]
    behavior_names = {
        B_IDLE: '休息中', B_WALK: '散步中', B_SLEEP: '睡觉中',
        B_HAPPY: '很开心', B_SAD: '需要陪伴', B_SURPRISED: '吓一跳',
        B_PETTING: '享受摸摸', B_LIFT: '被提起来啦',
    }

    panel_w, panel_h = 172, 136
    pad, radius = 12, 12
    px, py = _status_rect(center).topleft

    # 柔光晕圈代替深色投影
    translucent_rounded(surface, (202, 172, 216, 60),
                        (px - 6, py - 6, panel_w + 12, panel_h + 12), radius + 6)
    # 象牙白→淡蔚蓝渐变面板
    gradient_rounded(surface, (px, py, panel_w, panel_h), radius,
                     (250, 249, 242, 242), (223, 232, 241, 242))
    title = _font(13, bold=True).render(
        behavior_names.get(pet.behavior, '陪伴中'), True, (74, 92, 124)
    )
    surface.blit(title, (px + pad, py + 9))
    online = _font(10).render(mode_text, True, (96, 106, 132))
    online_x = px + panel_w - pad - online.get_width()
    pygame.draw.circle(surface, (143, 175, 126) if mode_text == '学习开启' else (172, 147, 190),
                       (online_x - 8, py + 16), 3)
    surface.blit(online, (online_x, py + 10))

    for i, (label, val, color) in enumerate(lines):
        ly = py + 36 + i * 24
        txt = font.render(label, True, (96, 106, 132))
        surface.blit(txt, (px + pad, ly))
        value_txt = _font(11, bold=True).render(f'{val:.0f}', True, color)
        surface.blit(value_txt, (px + panel_w - pad - value_txt.get_width(), ly + 1))

        bar_x, bar_y, bar_w, bar_h = px + 50, ly + 5, 88, 7
        pygame.draw.rect(surface, (226, 222, 236), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill_w = max(0, min(bar_w, int(bar_w * val / 100)))
        if fill_w > 0:
            pygame.draw.rect(surface, color, (bar_x, bar_y, fill_w, bar_h), border_radius=4)

    # 底部键盘快捷键提示
    pygame.draw.line(surface, (208, 198, 224),
                     (px + pad, py + panel_h - 30),
                     (px + panel_w - pad, py + panel_h - 30))
    button = get_feed_button_rect(pet, center)
    hovered = getattr(pet, 'feed_hovered', False)
    pygame.draw.rect(surface, (233, 207, 163) if hovered else (242, 226, 199),
                     button, border_radius=7)
    label = _font(12, bold=True).render(f'喂食  +{FEED_HUNGER_BOOST}   ·   F', True, (135, 100, 57))
    surface.blit(label, label.get_rect(center=button.center))


# ════════════════════════════════════════════
# 单词气泡
# ════════════════════════════════════════════

# 莫奈卡片：象牙白→薰衣草渐变，柔边描色
_WORD_BUBBLE_TOP = (251, 248, 240, 243)
_WORD_BUBBLE_BOTTOM = (227, 215, 235, 243)
_WORD_BUBBLE_TAIL = (231, 220, 238)
_WORD_BUBBLE_BORDER = (196, 178, 214, 140)
_WORD_FONT_SIZE = 26
_WORD_MEANING_FONT_SIZE = 16
_BUBBLE_PAD = 14
_BUBBLE_RADIUS = 10
_BUBBLE_LINE_GAP = 8
_BUBBLE_MAX_TEXT_W = 300
_BUBBLE_TAIL_H = 9


def _wrap_text(font, text, max_width):
    """按实际像素宽度换行，兼容中英文混排。"""
    if not text:
        return []
    lines, current = [], ''
    for char in text:
        candidate = current + char
        if current and font.size(candidate)[0] > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines[:3]


def _word_bubble_layout(word_data, progress_text=''):
    return _cached_word_bubble_layout(word_data['word'], word_data.get('meaning', ''), progress_text)


@lru_cache(maxsize=32)
def _cached_word_bubble_layout(word, meaning, progress_text=''):
    """返回气泡布局，绘制与点击检测共用同一份几何信息。"""
    word_size = _WORD_FONT_SIZE
    word_font = _font(word_size, bold=True)
    while word_size > 18 and word_font.size(word)[0] > _BUBBLE_MAX_TEXT_W:
        word_size -= 1
        word_font = _font(word_size, bold=True)
    meaning_font = _font(_WORD_MEANING_FONT_SIZE)
    hint_font = _font(11)

    word_surf = word_font.render(word, True, (52, 110, 180))
    meaning_lines = _wrap_text(meaning_font, meaning, _BUBBLE_MAX_TEXT_W)
    meaning_surfs = [meaning_font.render(line, True, (96, 106, 132)) for line in meaning_lines]
    hint = '点击卡片继续'
    hint_surf = hint_font.render(hint, True, (152, 160, 184))

    progress_w = hint_font.size(progress_text)[0] + 22 if progress_text else 0
    widths = [word_surf.get_width(), hint_surf.get_width(), progress_w + 70]
    widths.extend(s.get_width() for s in meaning_surfs)
    w = min(WINDOW_WIDTH - 24, max(180, max(widths) + _BUBBLE_PAD * 2))
    content_h = _BUBBLE_PAD + 18 + 10 + word_surf.get_height()
    if meaning_surfs:
        content_h += _BUBBLE_LINE_GAP + sum(s.get_height() for s in meaning_surfs)
        content_h += max(0, len(meaning_surfs) - 1) * 3
    content_h += 10 + hint_surf.get_height() + _BUBBLE_PAD
    bx = PET_CENTER_X - w // 2
    by = PET_CENTER_Y - 72 - content_h - _BUBBLE_TAIL_H
    rect = pygame.Rect(bx, by, w, content_h + _BUBBLE_TAIL_H)
    return rect, word_surf, meaning_surfs, hint_surf


def _position_bubble(rect, center=None):
    if center is None:
        return rect
    rect = rect.copy()
    cx, cy = center
    rect.x = max(8, min(WINDOW_WIDTH - rect.width - 8, cx - rect.width // 2))
    rect.y = cy - 72 - rect.height
    if rect.y < 8:
        rect.y = cy + 112
    rect.y = max(8, min(WINDOW_HEIGHT - rect.height - 8, rect.y))
    return rect


def get_word_bubble_rect(word_data, progress_text='', center=None):
    """提供与视觉完全一致的点击区域。"""
    if word_data is None:
        return pygame.Rect(0, 0, 0, 0)
    return _position_bubble(_word_bubble_layout(word_data, progress_text)[0], center)


def draw_word_bubble(surface, word_data, progress_text='', center=None):
    """在宠物上方绘制可点击的单词学习卡片。"""
    if word_data is None:
        return
    rect, word_surf, meaning_surfs, hint_surf = _word_bubble_layout(word_data, progress_text)
    rect = _position_bubble(rect, center)
    bx, by, w, total_h = rect
    h = total_h - _BUBBLE_TAIL_H
    tail_above = center is not None and rect.top > center[1]
    if tail_above:
        by += _BUBBLE_TAIL_H

    # 背景：柔光晕圈 + 象牙白→薰衣草渐变卡片 + 柔边描色
    radius = _BUBBLE_RADIUS
    translucent_rounded(surface, (202, 172, 216, 55),
                        (bx - 6, by - 4, w + 12, h + 12), radius + 6)
    gradient_rounded(surface, (bx, by, w, h), radius,
                     _WORD_BUBBLE_TOP, _WORD_BUBBLE_BOTTOM)

    # 小三角（指向宠物），取渐变底色
    tri_cx = bx + w // 2
    tri_y = by + 1 if tail_above else by + h - 1
    tri_size = _BUBBLE_TAIL_H
    pygame.draw.polygon(surface, _WORD_BUBBLE_TAIL,
                        [(tri_cx - tri_size, tri_y),
                         (tri_cx + tri_size, tri_y),
                         (tri_cx, tri_y - tri_size if tail_above else tri_y + tri_size)])
    translucent_rounded(surface, _WORD_BUBBLE_BORDER, (bx, by, w, h), radius, width=1)

    # 顶部标签和学习进度
    top_font = _font(11)
    top_label = top_font.render('今日单词', True, (140, 150, 178))
    surface.blit(top_label, (bx + _BUBBLE_PAD, by + _BUBBLE_PAD))
    if progress_text:
        progress_surf = top_font.render(progress_text, True, (52, 110, 180))
        pill_w = progress_surf.get_width() + 16
        pill_h = progress_surf.get_height() + 6
        pill_x = bx + w - _BUBBLE_PAD - pill_w
        pill_y = by + _BUBBLE_PAD - 3
        pygame.draw.rect(surface, (198, 222, 246),
                         (pill_x, pill_y, pill_w, pill_h), border_radius=8)
        surface.blit(progress_surf, (pill_x + 8, pill_y + 3))

    # 单词文字
    word_x = bx + _BUBBLE_PAD
    text_y = by + _BUBBLE_PAD + 28
    surface.blit(word_surf, (word_x, text_y))

    # 释义文字
    text_y += word_surf.get_height() + _BUBBLE_LINE_GAP
    for meaning_surf in meaning_surfs:
        meaning_x = bx + _BUBBLE_PAD
        surface.blit(meaning_surf, (meaning_x, text_y))
        text_y += meaning_surf.get_height() + 3

    hint_y = by + h - _BUBBLE_PAD - hint_surf.get_height()
    # 分隔线兼学习进度条：薰衣草轨道 + 蔚蓝填充
    track_y = hint_y - 6
    tx0, tx1 = bx + _BUBBLE_PAD, bx + w - _BUBBLE_PAD
    pygame.draw.line(surface, (210, 204, 226), (tx0, track_y), (tx1, track_y), 2)
    if progress_text and '/' in progress_text:
        try:
            cur_s, total_s = progress_text.split('/', 1)
            frac = max(0.0, min(1.0, int(cur_s) / max(1, int(total_s))))
            if frac > 0:
                pygame.draw.line(surface, (74, 144, 217),
                                 (tx0, track_y),
                                 (tx0 + int((tx1 - tx0) * frac), track_y), 2)
        except ValueError:
            pass  # 进度文本不是 "n/m" 格式时只画轨道
    surface.blit(hint_surf, (bx + _BUBBLE_PAD, hint_y))
    key_surf = _font(10, bold=True).render('SPACE', True, (90, 105, 140))
    key_w, key_h = key_surf.get_width() + 12, key_surf.get_height() + 4
    key_x = bx + w - _BUBBLE_PAD - key_w
    pygame.draw.rect(surface, (236, 240, 248),
                     (key_x, hint_y - 2, key_w, key_h), border_radius=5)
    pygame.draw.rect(surface, (196, 178, 214),
                     (key_x, hint_y - 2, key_w, key_h), 1, border_radius=5)
    surface.blit(key_surf, (key_x + 6, hint_y))
