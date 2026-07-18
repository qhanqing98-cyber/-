# character.py — GIF 桌宠绘制

import os

import pygame

from config import *

# ─── 精灵图缓存 ──────────────────────────────
_sprite_cache = {}
_flipped_cache = {}
_use_sprites = False
_font_cache = {}


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
    except ImportError:
        return False

    import numpy as np

    _sprite_cache.clear()
    _flipped_cache.clear()
    _use_sprites = False

    loaded_any = False
    for fname in sorted(gif_files):
        anim_name = os.path.splitext(fname)[0]  # 'walk' from 'walk.gif'
        path = os.path.join(gifs_path, fname)
        try:
            pil_gif = Image.open(path)
            frames = []
            n_frames = getattr(pil_gif, 'n_frames', 1)
            trans_idx = pil_gif.info.get('transparency', -1)

            for i in range(n_frames):
                pil_gif.seek(i)
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
                    pil_frame = Image.fromarray(rgba_arr, 'RGBA')
                else:
                    pil_frame = frame.convert('RGBA')

                # 缩放到合适大小（限制高度 200px 以内，保持比例）
                target_h = 200
                w, h = pil_frame.size
                if h > target_h:
                    scale = target_h / h
                    new_w = max(1, int(w * scale))
                    pil_frame = pil_frame.resize((new_w, target_h), Image.LANCZOS)

                # 叠加到品红背景上，消除半透明边缘的紫边
                rgba_arr = np.array(pil_frame, dtype=np.uint8)  # (H, W, 4)
                alpha = rgba_arr[:,:,3]
                rgba_arr[alpha < 128] = [255, 0, 255, 255]  # 半透明→品红（颜色键透明）
                rgba_arr[alpha >= 128, 3] = 255             # 不透明→全实心
                pil_frame = Image.fromarray(rgba_arr, 'RGBA').convert('RGB')

                # PIL → pygame Surface
                mode = pil_frame.mode
                size = pil_frame.size
                data = pil_frame.tobytes()
                surf = pygame.image.fromstring(data, size, mode)
                # 翻转使角色默认朝右（GIF 源默认朝左）
                surf = pygame.transform.flip(surf, True, False)
                frames.append(surf)

            if frames:
                groups = {anim_name: frames}
                _sprite_cache.update(groups)
                for an, f_list in groups.items():
                    _flipped_cache[an] = [pygame.transform.flip(f, True, False) for f in f_list]
                loaded_any = True
                print(f'  [GIF] {fname}: {n_frames} frames, {frames[0].get_width()}x{frames[0].get_height()}')

        except Exception as e:
            print(f'  [GIF] Failed to load {fname}: {e}')

    if loaded_any:
        _use_sprites = True
        return True
    return False


# ════════════════════════════════════════════
# 主绘制入口
# ════════════════════════════════════════════

def draw_pet(surface, pet):
    """绘制宠物（GIF 精灵图）"""
    _draw_sprite(surface, pet)


_anim_timers = {}

def _get_anim_speed(anim_name):
    speeds = {
        B_IDLE: 3,
        B_WALK: 3,
        B_SLEEP: 3,
        B_HAPPY: 4,
        B_SAD: 6,
        B_SURPRISED: 4,
        'happy_jump': 3,
        'happy_land': 4,
    }
    return speeds.get(anim_name, 6)


def _draw_sprite(surface, pet):
    global _anim_timers
    anim = pet.get_anim_name()

    if anim not in _anim_timers:
        _anim_timers[anim] = 0

    frames = _sprite_cache.get(anim)
    if not frames:
        frames = _sprite_cache.get(B_IDLE)
        anim = B_IDLE
    if not frames:
        return

    speed = _get_anim_speed(anim)
    _anim_timers[anim] += 1

    idx = (_anim_timers[anim] // speed) % len(frames)

    if pet.direction < 0:
        flipped_frames = _flipped_cache.get(anim)
        if flipped_frames:
            img = flipped_frames[idx]
        else:
            img = frames[idx]
    else:
        img = frames[idx]

    rect = img.get_rect(center=(PET_CENTER_X, PET_CENTER_Y))
    surface.blit(img, rect)


def draw_feedback(surface, pet):
    """绘制互动反馈（粒子和浮动文字）"""
    if not pet.feedback_items:
        return
    font = _font(16, bold=True)
    for item in pet.feedback_items:
        alpha = int(item['alpha'] * 255)
        if item['type'] == 'text':
            r, g, b = item['color']
            txt = font.render(item['text'], True, (r, g, b, alpha))
            surface.blit(txt, (item['x'], item['y']))
        elif item['type'] == 'particle':
            r, g, b = item['color']
            s = pygame.Surface((item['size'] * 2, item['size'] * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (r, g, b, alpha), (item['size'], item['size']), item['size'])
            surface.blit(s, (item['x'] - item['size'], item['y'] - item['size']))


# ════════════════════════════════════════════
# 悬停状态面板
# ════════════════════════════════════════════

def _draw_rounded_bar(self, surf, color, x, y, w, h, radius, progress):
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (50, 50, 55, 180), (0, 0, w, h), 0, radius)
    surf.blit(bg, (x, y))

    if progress <= 0:
        return

    fill_w = int(w * progress)
    fill_surface = pygame.Surface((fill_w, h), pygame.SRCALPHA)

    if progress < 0.3:
        gradient_color = (255, 80, 80)
    elif progress < 0.6:
        gradient_color = (255, 200, 80)
    else:
        gradient_color = (100, 220, 100)

    for i in range(fill_w):
        alpha = 180 + 75 * (i / fill_w)
        r, g, b = gradient_color
        fill_surface.set_at((i, h // 2), (r, g, b, int(alpha)))

    pygame.draw.rect(fill_surface, gradient_color, (0, 0, fill_w, h), 0, radius)
    highlight = pygame.Surface((fill_w, h // 2), pygame.SRCALPHA)
    pygame.draw.rect(highlight, (255, 255, 255, 30), (0, 0, fill_w, h // 2), 0, radius)
    fill_surface.blit(highlight, (0, 0))

    surf.blit(fill_surface, (x, y))


def draw_status(surface, pet):
    if not pet.is_hovered or pet.word_bubble_active:
        return

    font = _font(12)
    lines = [
        ('饱食', pet.hunger, (255, 170, 92)),
        ('心情', pet.mood, (255, 112, 153)),
        ('精力', pet.energy, (94, 185, 255)),
    ]
    behavior_names = {
        B_IDLE: '休息中', B_WALK: '散步中', B_SLEEP: '睡觉中',
        B_HAPPY: '很开心', B_SAD: '需要陪伴', B_SURPRISED: '吓一跳',
    }

    panel_w, panel_h = 172, 116
    pad, radius = 12, 12
    px = min(WINDOW_WIDTH - panel_w - 8, PET_CENTER_X + 42)
    py = PET_CENTER_Y - panel_h - 54

    shadow = pygame.Surface((panel_w + 8, panel_h + 8), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 70), (4, 4, panel_w, panel_h), border_radius=radius)
    surface.blit(shadow, (px - 4, py - 3))

    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (27, 29, 38, 238), bg.get_rect(), border_radius=radius)
    pygame.draw.rect(bg, (91, 98, 122, 150), bg.get_rect(), 1, border_radius=radius)
    title = _font(13, bold=True).render(
        behavior_names.get(pet.behavior, '陪伴中'), True, (245, 247, 255)
    )
    bg.blit(title, (pad, 9))
    online = _font(10).render('在线', True, (142, 154, 181))
    online_x = panel_w - pad - online.get_width()
    pygame.draw.circle(bg, (104, 226, 163), (online_x - 8, 16), 3)
    bg.blit(online, (online_x, 10))
    surface.blit(bg, (px, py))

    for i, (label, val, color) in enumerate(lines):
        ly = py + 36 + i * 24
        txt = font.render(label, True, (230, 230, 230))
        surface.blit(txt, (px + pad, ly))
        value_txt = _font(11, bold=True).render(f'{val:.0f}', True, color)
        surface.blit(value_txt, (px + panel_w - pad - value_txt.get_width(), ly + 1))

        bar_x, bar_y, bar_w, bar_h = px + 50, ly + 5, 88, 7
        pygame.draw.rect(surface, (55, 59, 72), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill_w = max(0, min(bar_w, int(bar_w * val / 100)))
        if fill_w > 0:
            pygame.draw.rect(surface, color, (bar_x, bar_y, fill_w, bar_h), border_radius=4)


# ════════════════════════════════════════════
# 单词气泡
# ════════════════════════════════════════════

_WORD_BUBBLE_BG = (40, 40, 50)
_WORD_BUBBLE_BORDER = (100, 100, 130)
_WORD_FONT_SIZE = 26
_WORD_MEANING_FONT_SIZE = 16
_BUBBLE_PAD = 14
_BUBBLE_RADIUS = 10
_BUBBLE_LINE_GAP = 8
_BUBBLE_MAX_TEXT_W = 300
_BUBBLE_TAIL_H = 9


def _draw_rounded_rect_static(surf, color, rect, radius):
    """绘制纯色圆角矩形（无边框）"""
    x, y, w, h = rect
    pygame.draw.rect(surf, color, (x + radius, y, w - radius * 2, h))
    pygame.draw.rect(surf, color, (x, y + radius, w, h - radius * 2))
    pygame.draw.circle(surf, color, (x + radius, y + radius), radius)
    pygame.draw.circle(surf, color, (x + w - radius, y + radius), radius)
    pygame.draw.circle(surf, color, (x + radius, y + h - radius), radius)
    pygame.draw.circle(surf, color, (x + w - radius, y + h - radius), radius)


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
    """返回气泡布局，绘制与点击检测共用同一份几何信息。"""
    word = word_data['word']
    meaning = word_data.get('meaning', '')
    word_size = _WORD_FONT_SIZE
    word_font = _font(word_size, bold=True)
    while word_size > 18 and word_font.size(word)[0] > _BUBBLE_MAX_TEXT_W:
        word_size -= 1
        word_font = _font(word_size, bold=True)
    meaning_font = _font(_WORD_MEANING_FONT_SIZE)
    hint_font = _font(11)

    word_surf = word_font.render(word, True, (255, 255, 255))
    meaning_lines = _wrap_text(meaning_font, meaning, _BUBBLE_MAX_TEXT_W)
    meaning_surfs = [meaning_font.render(line, True, (198, 203, 225)) for line in meaning_lines]
    hint = '点击卡片继续'
    hint_surf = hint_font.render(hint, True, (133, 145, 178))

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


def get_word_bubble_rect(word_data, progress_text=''):
    """提供与视觉完全一致的点击区域。"""
    if word_data is None:
        return pygame.Rect(0, 0, 0, 0)
    return _word_bubble_layout(word_data, progress_text)[0]


def draw_word_bubble(surface, word_data, progress_text=''):
    """在宠物上方绘制可点击的单词学习卡片。"""
    if word_data is None:
        return
    rect, word_surf, meaning_surfs, hint_surf = _word_bubble_layout(word_data, progress_text)
    bx, by, w, total_h = rect
    h = total_h - _BUBBLE_TAIL_H

    # 背景
    radius = _BUBBLE_RADIUS
    bg = pygame.Surface((w, total_h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (0, 0, 0, 55), (3, 4, w - 6, h), border_radius=radius)
    _draw_rounded_rect_static(bg, (*_WORD_BUBBLE_BG, 235), (0, 0, w, h), radius)
    pygame.draw.rect(bg, (*_WORD_BUBBLE_BORDER, 190), (0, 0, w, h), 1, border_radius=radius)

    # 小三角（指向宠物）
    tri_cx = w // 2
    tri_y = h - 1
    tri_size = _BUBBLE_TAIL_H
    pygame.draw.polygon(bg, (*_WORD_BUBBLE_BG, 235),
                        [(tri_cx - tri_size, tri_y),
                         (tri_cx + tri_size, tri_y),
                         (tri_cx, tri_y + tri_size)])

    surface.blit(bg, (bx, by))

    # 顶部标签和学习进度
    top_font = _font(11)
    top_label = top_font.render('今日单词', True, (133, 145, 178))
    surface.blit(top_label, (bx + _BUBBLE_PAD, by + _BUBBLE_PAD))
    if progress_text:
        progress_surf = top_font.render(progress_text, True, (210, 218, 255))
        pill_w = progress_surf.get_width() + 16
        pill_h = progress_surf.get_height() + 6
        pill_x = bx + w - _BUBBLE_PAD - pill_w
        pill_y = by + _BUBBLE_PAD - 3
        pygame.draw.rect(surface, (64, 75, 118),
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
    pygame.draw.line(surface, (71, 76, 94),
                     (bx + _BUBBLE_PAD, hint_y - 6),
                     (bx + w - _BUBBLE_PAD, hint_y - 6))
    surface.blit(hint_surf, (bx + _BUBBLE_PAD, hint_y))
    key_surf = _font(10, bold=True).render('SPACE', True, (174, 184, 215))
    key_w, key_h = key_surf.get_width() + 12, key_surf.get_height() + 4
    key_x = bx + w - _BUBBLE_PAD - key_w
    pygame.draw.rect(surface, (55, 60, 76),
                     (key_x, hint_y - 2, key_w, key_h), border_radius=5)
    pygame.draw.rect(surface, (89, 96, 119),
                     (key_x, hint_y - 2, key_w, key_h), 1, border_radius=5)
    surface.blit(key_surf, (key_x + 6, hint_y))
