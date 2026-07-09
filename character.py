# character.py — 角色绘制（程序绘制 + 精灵图加载）

import math
import os

import pygame

from config import *

# ─── 精灵图缓存 ──────────────────────────────
_sprite_cache = {}
_flipped_cache = {}
_use_sprites = False


# ════════════════════════════════════════════
# 精灵图加载
# ════════════════════════════════════════════

def load_sprites():
    global _sprite_cache, _flipped_cache, _use_sprites
    _sprite_cache.clear()
    _flipped_cache.clear()
    _use_sprites = False
    sprites_path = os.path.join(os.path.dirname(__file__), SPRITES_DIR)
    if not os.path.isdir(sprites_path):
        return
    files = [f for f in os.listdir(sprites_path)
             if f.lower().endswith(('.png', '.bmp', '.jpg'))]
    if not files:
        return
    groups = {}
    for fname in sorted(files):
        stem, _ = os.path.splitext(fname)
        parts = stem.rsplit('_', 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        anim = parts[0]
        img = pygame.image.load(os.path.join(sprites_path, fname)).convert_alpha()
        groups.setdefault(anim, []).append(img)
    if groups:
        _sprite_cache = groups
        for anim_name, frames in groups.items():
            _flipped_cache[anim_name] = [pygame.transform.flip(f, True, False) for f in frames]
        _use_sprites = True


def has_sprites():
    return _use_sprites


# ════════════════════════════════════════════
# 主绘制入口
# ════════════════════════════════════════════

def draw_pet(surface, pet):
    if _use_sprites:
        _draw_sprite(surface, pet)
    else:
        _draw_default(surface, pet)


_anim_timers = {}

def _get_anim_speed(anim_name):
    speeds = {
        B_IDLE: 8,
        B_WALK: 3,
        B_SLEEP: 12,
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


# ════════════════════════════════════════════
# 默认程序绘制 — Q版小猫（大头大眼小身体）
# ════════════════════════════════════════════

def _draw_default(surface, pet):
    anim = pet.get_anim_name()
    frame = pet.frame

    bob = math.sin(frame * 0.08) * 2 if anim in (B_IDLE, B_WALK) else 0
    blink = (frame % 180) >= 178

    eye_style = 'normal'
    mouth_style = 'smile'
    ear_droop = False
    sleep_z = False
    jump_offset = 0
    sway = 0

    if anim == B_SLEEP:
        eye_style = 'closed'
        mouth_style = 'none'
        bob = math.sin(frame * 0.03) * 3
        sleep_z = pet.sleep_z_visible
    elif anim == B_HAPPY or anim == 'happy_jump':
        eye_style = 'happy'
        mouth_style = 'open_smile'
        jump_offset = -math.sin(min(frame / 30.0, 1.0) * math.pi) * 18
    elif anim == 'happy_land':
        eye_style = 'happy'
        mouth_style = 'open_smile'
    elif anim == B_SAD:
        eye_style = 'sad'
        mouth_style = 'frown'
        ear_droop = True
        bob = math.sin(frame * 0.05) * 1
    elif anim == B_SURPRISED:
        eye_style = 'surprised'
        mouth_style = 'open'
        jump_offset = -math.sin(min(frame / 15.0, 1.0) * math.pi) * 12
    elif anim == B_WALK:
        sway = math.sin(frame * 0.15) * 3

    cx, cy = PET_CENTER_X, PET_CENTER_Y + jump_offset
    if blink and eye_style == 'normal':
        eye_style = 'blink'

    # 头部中心（Q版：大头在上）
    head_y = cy - 22 + bob

    # ── 绘制顺序：从后往前 ──
    # 1. 尾巴
    _draw_tail(surface, cx, head_y + 40, bob, -pet.direction, sway)
    # 2. 后腿
    leg_sway = math.sin(frame * 0.15) * 2 if anim == B_WALK else 0
    _draw_leg(surface, cx - 12, head_y + 42, leg_sway, False)
    _draw_leg(surface, cx + 12, head_y + 42, -leg_sway, False)
    # 3. 身体（Q版：小身体在大头下面）
    _draw_body(surface, cx, head_y + 18)
    # 4. 耳朵
    _draw_ears(surface, cx, head_y - 26, ear_droop)
    # 5. 大头
    _draw_head(surface, cx, head_y)
    # 6. 眼睛（Q版：超大眼）
    _draw_eyes(surface, cx, head_y - 1, eye_style, pet.direction)
    # 7. 腮红
    _draw_cheeks(surface, cx, head_y + 4)
    # 8. 鼻子
    _draw_nose(surface, (cx, head_y + 6))
    # 9. 嘴
    _draw_mouth(surface, cx, head_y + 10, mouth_style)
    # 10. 前腿
    _draw_leg(surface, cx - 10, head_y + 40, leg_sway, True)
    _draw_leg(surface, cx + 10, head_y + 40, -leg_sway, True)
    # 11. Z
    if sleep_z:
        _draw_z(surface, cx + 30, head_y - 32)


# ─── 子绘制 ──────────────────────────────────

def _draw_head(surface, cx, cy):
    """Q版大头"""
    pygame.draw.circle(surface, BODY_COLOR, (cx, cy), 28)
    # 额头高光
    pygame.draw.circle(surface, BELLY_COLOR, (cx - 4, cy - 10), 10)

def _draw_body(surface, cx, cy):
    """Q版小身体"""
    body_rect = pygame.Rect(cx - 22, cy - 2, 44, 34)
    pygame.draw.ellipse(surface, BODY_COLOR, body_rect)
    # 肚子
    belly_rect = pygame.Rect(cx - 14, cy + 4, 28, 22)
    pygame.draw.ellipse(surface, BELLY_COLOR, belly_rect)

def _draw_tail(surface, cx, cy, bob, direction, sway):
    tail_rect = pygame.Rect(cx + direction * 22 + sway, cy - 6, 14, 10)
    try:
        pygame.draw.arc(surface, BODY_COLOR, tail_rect, 0.3, 2.8, 3)
    except ValueError:
        pass

def _draw_leg(surface, x, y, sway, front):
    size = (10, 8) if front else (8, 7)
    leg_rect = pygame.Rect(x + sway, y, size[0], size[1])
    pygame.draw.ellipse(surface, BODY_COLOR, leg_rect)

def _draw_ears(surface, cx, cy_top, droop):
    off = 3 if droop else 0
    # 左耳 - 小巧三角形
    pygame.draw.polygon(surface, EAR_COLOR, [
        (cx - 22, cy_top - 6 - off),
        (cx - 30, cy_top + 4),
        (cx - 14, cy_top + 4)])
    pygame.draw.polygon(surface, INNER_EAR_COLOR, [
        (cx - 22, cy_top - 3 - off),
        (cx - 27, cy_top + 2),
        (cx - 16, cy_top + 2)])
    # 右耳
    pygame.draw.polygon(surface, EAR_COLOR, [
        (cx + 22, cy_top - 6 - off),
        (cx + 30, cy_top + 4),
        (cx + 14, cy_top + 4)])
    pygame.draw.polygon(surface, INNER_EAR_COLOR, [
        (cx + 22, cy_top - 3 - off),
        (cx + 27, cy_top + 2),
        (cx + 16, cy_top + 2)])

def _draw_eyes(surface, cx, cy, style, direction):
    le = -13; re = 13; r = 9  # Q版大眼
    if style == 'blink':
        pygame.draw.ellipse(surface, EYE_COLOR, (cx + le - 8, cy - 1, 16, 4))
        pygame.draw.ellipse(surface, EYE_COLOR, (cx + re - 8, cy - 1, 16, 4))
    elif style == 'happy':
        pygame.draw.arc(surface, EYE_COLOR, (cx + le - 8, cy - 5, 16, 12),
                        3.8, 5.6, 3)
        pygame.draw.arc(surface, EYE_COLOR, (cx + re - 8, cy - 5, 16, 12),
                        3.8, 5.6, 3)
    elif style == 'sad':
        pygame.draw.arc(surface, EYE_COLOR, (cx + le - 9, cy - 4, 16, 12),
                        0.8, 2.8, 3)
        pygame.draw.arc(surface, EYE_COLOR, (cx + re - 7, cy - 4, 16, 12),
                        3.5, 5.5, 3)
    elif style == 'surprised':
        pygame.draw.circle(surface, EYE_COLOR, (cx + le, cy), r + 1)
        pygame.draw.circle(surface, EYE_COLOR, (cx + re, cy), r + 1)
        # 大高光
        pygame.draw.circle(surface, (255, 255, 255), (cx + le - 3, cy - 4), 4)
        pygame.draw.circle(surface, (255, 255, 255), (cx + re - 3, cy - 4), 4)
    elif style == 'closed':
        pygame.draw.ellipse(surface, EYE_COLOR, (cx + le - 8, cy - 3, 16, 5))
        pygame.draw.ellipse(surface, EYE_COLOR, (cx + re - 8, cy - 3, 16, 5))
    else:  # normal — 超大眼睛
        # 眼白
        pygame.draw.circle(surface, (255, 255, 255), (cx + le, cy), r)
        pygame.draw.circle(surface, (255, 255, 255), (cx + re, cy), r)
        # 瞳孔（大）
        pygame.draw.circle(surface, EYE_COLOR, (cx + le, cy), r - 2)
        pygame.draw.circle(surface, EYE_COLOR, (cx + re, cy), r - 2)
        # 大高光
        hx = 2 * direction
        pygame.draw.circle(surface, (255, 255, 255),
                           (cx + le + hx, cy - 4), 3)
        pygame.draw.circle(surface, (255, 255, 255),
                           (cx + re + hx, cy - 4), 3)
        # 小高光
        pygame.draw.circle(surface, (255, 255, 255),
                           (cx + le - 2, cy + 2), 1)
        pygame.draw.circle(surface, (255, 255, 255),
                           (cx + re - 2, cy + 2), 1)

def _draw_cheeks(surface, cx, cy):
    for dx in (-18, 6):
        s = pygame.Surface((14, 10), pygame.SRCALPHA)
        pygame.draw.circle(s, (*CHEEK_COLOR, 100), (7, 5), 5)
        surface.blit(s, (cx + dx, cy))

def _draw_nose(surface, pos):
    x, y = pos
    pygame.draw.polygon(surface, NOSE_COLOR, [
        (x, y - 2), (x - 2, y + 1), (x + 2, y + 1)])

def _draw_mouth(surface, cx, cy, style):
    if style == 'smile':
        pygame.draw.arc(surface, MOUTH_COLOR,
                        (cx - 5, cy - 1, 10, 6), 0, math.pi, 2)
    elif style == 'open_smile':
        pygame.draw.ellipse(surface, (200, 80, 80), (cx - 4, cy, 8, 6))
        pygame.draw.ellipse(surface, (255, 180, 180), (cx - 3, cy + 2, 6, 3))
    elif style == 'frown':
        pygame.draw.arc(surface, MOUTH_COLOR,
                        (cx - 5, cy - 2, 10, 6), math.pi, 2 * math.pi, 2)
    elif style == 'open':
        pygame.draw.ellipse(surface, (100, 80, 70), (cx - 3, cy - 1, 6, 6))

def _draw_z(surface, x, y):
    """睡眠 Z 气泡"""
    font = pygame.font.SysFont('simsun', 14, bold=True)
    font_big = pygame.font.SysFont('simsun', 20, bold=True)
    r, g, b = SLEEP_Z_COLOR
    for i in range(3):
        alpha = 60 + 60 * (i + 1)
        zs = font.render('z', True, (r, g, b, min(255, alpha)))
        surface.blit(zs, (x + i * 8, y - i * 10))
    t = (pygame.time.get_ticks() % 2000) / 2000.0
    big_alpha = int(80 + 120 * t)
    z_big = font_big.render('Z', True, (r, g, b, min(255, big_alpha)))
    surface.blit(z_big, (x + 24, y - 30))


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
