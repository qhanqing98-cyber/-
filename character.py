# character.py — GIF 桌宠绘制

import os

import pygame

from config import *

# ─── 精灵图缓存 ──────────────────────────────
_sprite_cache = {}
_flipped_cache = {}
_use_sprites = False


# ════════════════════════════════════════════
# GIF 动画加载（gifs/ 目录，一个 .gif 对应一个行为）
# ════════════════════════════════════════════


def load_gifs(gif_dir='gifs'):
    """从 gifs/ 目录加载 GIF 作为精灵图动画。

    命名规则：walk.gif → 动画名 'walk'，所有帧作为该动画帧序列。
    若 gifs/ 存在且有 .gif 文件，则加载并启用精灵模式。
    """
    global _sprite_cache, _flipped_cache, _use_sprites
    gifs_path = os.path.join(os.path.dirname(__file__), gif_dir)
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
    font = pygame.font.SysFont('simsun', 16, bold=True)
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
    if not pet.is_hovered:
        return

    font = pygame.font.SysFont('simsun', 12)
    lines = [
        ('\u9971\u9913', pet.hunger, (255, 160, 80)),
        ('\u5fc3\u60c5', pet.mood, (255, 120, 160)),
        ('\u7cbe\u529b', pet.energy, (120, 200, 255)),
    ]

    panel_w = 120
    bar_w = 60
    line_h = 20
    pad = 8
    panel_h = len(lines) * line_h + pad * 2
    radius = 8

    px = PET_CENTER_X + 25
    py = PET_CENTER_Y - 40 - panel_h

    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    pygame.draw.rect(bg, (30, 30, 35, 220), (0, 0, panel_w, panel_h), 0, radius)
    pygame.draw.rect(bg, (60, 60, 70, 150), (0, 0, panel_w, panel_h), 1, radius)

    shadow = pygame.Surface((panel_w + 4, panel_h + 4), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 60), (2, 2, panel_w, panel_h), 0, radius)
    surface.blit(shadow, (px - 1, py - 1))

    surface.blit(bg, (px, py))

    for i, (label, val, color) in enumerate(lines):
        ly = py + pad + i * line_h

        icon_font = pygame.font.SysFont('simsun', 14)
        if label == '\u9971\u9913':
            icon = icon_font.render('\u1F35C', True, color)
        elif label == '\u5fc3\u60c5':
            icon = icon_font.render('\u2764\uFE0F', True, color)
        else:
            icon = icon_font.render('\u26A1', True, color)
        surface.blit(icon, (px + 6, ly - 1))

        txt = font.render(label, True, (230, 230, 230))
        surface.blit(txt, (px + 24, ly + 1))

        bar_x = px + 55
        bar_h = 8
        bar_y = ly + 4

        bar_bg = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(bar_bg, (50, 50, 55, 180), (0, 0, bar_w, bar_h), 0, 4)
        surface.blit(bar_bg, (bar_x, bar_y))

        fill_w = int(bar_w * val / 100)
        if fill_w > 0:
            fill_surface = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)

            if val < 30:
                gradient_start = (255, 80, 80)
                gradient_end = (255, 120, 120)
            elif val < 60:
                gradient_start = (255, 200, 80)
                gradient_end = (255, 160, 60)
            else:
                gradient_start = (100, 220, 100)
                gradient_end = (80, 180, 80)

            for j in range(fill_w):
                t = j / fill_w
                r = int(gradient_start[0] * (1 - t) + gradient_end[0] * t)
                g = int(gradient_start[1] * (1 - t) + gradient_end[1] * t)
                b = int(gradient_start[2] * (1 - t) + gradient_end[2] * t)
                for k in range(bar_h):
                    fill_surface.set_at((j, k), (r, g, b, 200))

            pygame.draw.rect(fill_surface, (255, 255, 255, 40), (0, 0, fill_w, bar_h // 2), 0, 4)

            pygame.draw.rect(fill_surface, gradient_start, (0, 0, fill_w, bar_h), 0, 4)
            surface.blit(fill_surface, (bar_x, bar_y))

        num_font = pygame.font.SysFont('simsun', 10)
        num = num_font.render(f'{val:.0f}', True, (200, 200, 200))
        surface.blit(num, (bar_x + bar_w + 4, ly + 2))


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


def _draw_rounded_rect_static(surf, color, rect, radius):
    """绘制纯色圆角矩形（无边框）"""
    x, y, w, h = rect
    pygame.draw.rect(surf, color, (x + radius, y, w - radius * 2, h))
    pygame.draw.rect(surf, color, (x, y + radius, w, h - radius * 2))
    pygame.draw.circle(surf, color, (x + radius, y + radius), radius)
    pygame.draw.circle(surf, color, (x + w - radius, y + radius), radius)
    pygame.draw.circle(surf, color, (x + radius, y + h - radius), radius)
    pygame.draw.circle(surf, color, (x + w - radius, y + h - radius), radius)


def draw_word_bubble(surface, word_data):
    """在宠物上方绘制单词气泡"""
    if word_data is None:
        return

    word = word_data['word']
    meaning = word_data.get('meaning', '')

    word_font = pygame.font.SysFont('simsun', _WORD_FONT_SIZE, bold=True)
    meaning_font = pygame.font.SysFont('simsun', _WORD_MEANING_FONT_SIZE)

    word_surf = word_font.render(word, True, (255, 255, 255))
    meaning_surf = meaning_font.render(meaning, True, (200, 200, 230)) if meaning else None

    pw = _BUBBLE_PAD
    w = word_surf.get_width() + pw * 2
    h = word_surf.get_height() + pw * 2
    if meaning_surf:
        w = max(w, meaning_surf.get_width() + pw * 2)
        h += meaning_surf.get_height() + _BUBBLE_LINE_GAP

    # 最小宽度
    w = max(w, 80)

    # 气泡位置：宠物正上方
    bx = PET_CENTER_X - w // 2
    by = PET_CENTER_Y - 80 - h

    # 背景
    radius = _BUBBLE_RADIUS
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    _draw_rounded_rect_static(bg, (*_WORD_BUBBLE_BG, 235), (0, 0, w, h), radius)
    pygame.draw.rect(bg, (*_WORD_BUBBLE_BORDER, 180), (0, 0, w, h), 1, radius)

    # 小三角（指向宠物）
    tri_cx = w // 2
    tri_y = h
    tri_size = 8
    pygame.draw.polygon(bg, (*_WORD_BUBBLE_BG, 235),
                        [(tri_cx - tri_size, tri_y),
                         (tri_cx + tri_size, tri_y),
                         (tri_cx, tri_y + tri_size)])

    surface.blit(bg, (bx, by))

    # 单词文字
    word_x = bx + (w - word_surf.get_width()) // 2
    surface.blit(word_surf, (word_x, by + pw))

    # 释义文字
    if meaning_surf:
        meaning_x = bx + (w - meaning_surf.get_width()) // 2
        meaning_y = by + pw + word_surf.get_height() + _BUBBLE_LINE_GAP
        surface.blit(meaning_surf, (meaning_x, meaning_y))
