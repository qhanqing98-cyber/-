# ui_theme.py — 莫奈印象派风格 UI 主题
# 设计规则：柔和渐变替代硬边框、半透明分层造深度、
# 高调粉彩配色、柔光晕圈替代深色投影。

import pygame
from functools import lru_cache

# ─── 莫奈调色板 ───
CERULEAN = (74, 144, 217)       # 蔚蓝（正午天空与水面）
CERULEAN_DEEP = (52, 110, 180)  # 深蔚蓝（浅底上的强调文字）
LAVENDER = (200, 168, 212)      # 薰衣草（暮色雾气）
PALE_GOLD = (245, 217, 139)     # 淡金（晨光洒在水面）
SAGE = (143, 175, 126)          # 鼠尾草绿（散射光下的叶丛）
CORAL = (232, 144, 122)         # 珊瑚粉（落日倒影）
CORAL_DEEP = (219, 116, 96)     # 深珊瑚（浅底上的警示文字）
IVORY = (250, 247, 238)         # 象牙白（饱和光的高光）
INK = (74, 88, 116)             # 浅底主文字（蓝灰墨色）
INK_SOFT = (146, 156, 182)      # 浅底次要文字


@lru_cache(maxsize=64)
def gradient_surface(w, h, top, bottom):
    """生成垂直渐变的 SRCALPHA 面。top/bottom 为 (r,g,b,a)。"""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for row in range(h):
        t = row / max(1, h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4))
        pygame.draw.line(surf, color, (0, row), (w, row))
    return surf


@lru_cache(maxsize=64)
def rounded_mask(w, h, radius):
    """圆角蒙版：内部不透明、四角透明，用于给任意面裁出圆角。"""
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255),
                     mask.get_rect(), border_radius=radius)
    return mask


def gradient_rounded(surf, rect, radius, top, bottom, glow=None):
    """在 surf 上绘制垂直渐变圆角面板。
    原理：先逐行画出渐变，再用 BLEND_RGBA_MULT 把渐变面的 alpha
    乘上圆角蒙版的 alpha，四角自然归零，得到平滑圆角。
    glow 为柔光晕圈颜色（RGBA），代替深色投影。"""
    x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    if w <= 0 or h <= 0:
        return
    if glow is not None:
        halo = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
        pygame.draw.rect(halo, glow, halo.get_rect(), border_radius=radius + 6)
        surf.blit(halo, (x - 6, y - 6))
    surf.blit(_rounded_gradient(w, h, radius, tuple(top), tuple(bottom)), (x, y))


@lru_cache(maxsize=64)
def _rounded_gradient(w, h, radius, top, bottom):
    grad = gradient_surface(w, h, top, bottom).copy()
    grad.blit(rounded_mask(w, h, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return grad


def translucent_rounded(surf, color, rect, radius, width=0):
    """半透明圆角矩形。直接在显示面上用 RGBA 色调用 pygame.draw
    会被忽略 alpha，所以必须经 SRCALPHA 临时面。"""
    x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    if w <= 0 or h <= 0:
        return
    surf.blit(_translucent_panel(w, h, tuple(color), radius, width), (x, y))


@lru_cache(maxsize=128)
def _translucent_panel(w, h, color, radius, width):
    temp = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(temp, color, temp.get_rect(), width, border_radius=radius)
    return temp
