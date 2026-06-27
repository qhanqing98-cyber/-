"""generate_sprites_from_ref.py — 从参考图生成 Q版精灵图"""

import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from PIL import Image
import numpy as np

REF_IMAGE = '.reasonix/attachments/clipboard-20260626-230535.101914-000001.webp'
OUT_DIR = 'sprites'
SPRITE_SIZE = 160

def load_and_clean():
    """加载参考图，去白底，裁剪到内容"""
    img = Image.open(REF_IMAGE).convert('RGBA')
    arr = np.array(img, dtype=np.uint8)
    
    # 白色/近白色 → 透明
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    white_mask = (r > 240) & (g > 240) & (b > 240)
    a[white_mask] = 0
    arr[:,:,3] = a
    
    img = Image.fromarray(arr, 'RGBA')
    
    # 裁剪到非透明内容
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    
    return img

def make_frame(base_img, offset_x=0, offset_y=0, scale=1.0, flip=False, 
               squeeze_x=1.0, squeeze_y=1.0):
    """从 base 生成一帧，支持位移/缩放/翻转/挤压"""
    w, h = base_img.size
    new_w = int(w * scale * squeeze_x)
    new_h = int(h * scale * squeeze_y)
    
    # 缩放
    if scale != 1.0 or squeeze_x != 1.0 or squeeze_y != 1.0:
        img = base_img.resize((max(1, new_w), max(1, new_h)), Image.LANCZOS)
    else:
        img = base_img.copy()
    
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    
    # 放到 160x160 画布中央 + 偏移
    canvas = Image.new('RGBA', (SPRITE_SIZE, SPRITE_SIZE), (0, 0, 0, 0))
    iw, ih = img.size
    cx = (SPRITE_SIZE - iw) // 2 + offset_x
    cy = (SPRITE_SIZE - ih) // 2 + offset_y
    canvas.paste(img, (cx, cy), img)
    
    return canvas

def save_frame(img, name):
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print(f'  {name}')

def generate():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # 清理旧精灵图
    for f in os.listdir(OUT_DIR):
        if f.endswith('.png'):
            os.remove(os.path.join(OUT_DIR, f))
    
    base = load_and_clean()
    print(f'Cleaned image: {base.size}')
    
    # 缩放到合适大小（猫占 90~110px 高）
    bw, bh = base.size
    target_h = 110
    scale = target_h / bh
    base = base.resize((int(bw * scale), target_h), Image.LANCZOS)
    print(f'Scaled to: {base.size}')
    
    # ── idle (4帧: 呼吸浮动) ──
    for f in range(4):
        phase = f / 4.0 * math.pi * 2
        bob = int(math.sin(phase) * 2)
        breath = 1.0 + math.sin(phase) * 0.03
        img = make_frame(base, offset_y=bob, scale=breath)
        save_frame(img, f'idle_{f}.png')
    
    # ── walk (6帧: 走路摇摆) ──
    for f in range(6):
        phase = f / 6.0 * math.pi * 2
        sway = int(math.sin(phase) * 4)
        bob = int(abs(math.sin(phase)) * 3 - 1.5)  # 上下弹跳
        squeeze = 1.0 + math.cos(phase) * 0.05      # 左右挤压
        img = make_frame(base, offset_x=sway, offset_y=bob, squeeze_x=squeeze)
        save_frame(img, f'walk_{f}.png')
    
    # ── walk_left (翻转版) ──
    # 不需要，运行时 direction<0 会自动 flip
    
    # ── sleep (2帧: 缓慢呼吸) ──
    for f in range(2):
        phase = f / 2.0 * math.pi
        bob = int(math.sin(phase) * 3)
        breath = 1.0 + math.sin(phase) * 0.04
        img = make_frame(base, offset_y=bob + 8, scale=breath * 0.85)
        save_frame(img, f'sleep_{f}.png')
    
    # ── happy_jump (3帧: 跳起) ──
    jump_heights = [-6, -16, -6]
    jump_scales = [1.08, 1.02, 1.08]
    for f in range(3):
        img = make_frame(base, offset_y=jump_heights[f], scale=jump_scales[f])
        save_frame(img, f'happy_jump_{f}.png')
    
    # ── happy_land (1帧) ──
    img = make_frame(base, offset_y=2, scale=0.95, squeeze_y=0.85)
    save_frame(img, 'happy_land_0.png')
    
    # ── sad (2帧: 垂头) ──
    for f in range(2):
        img = make_frame(base, offset_y=4 + f, scale=0.92)
        save_frame(img, f'sad_{f}.png')
    
    # ── surprised (2帧: 惊跳) ──
    for f in range(2):
        img = make_frame(base, offset_y=-8 + f * 3, scale=1.05)
        save_frame(img, f'surprised_{f}.png')
    
    count = len([f for f in os.listdir(OUT_DIR) if f.endswith('.png')])
    print(f'\nDone! {count} sprites')

if __name__ == '__main__':
    generate()
