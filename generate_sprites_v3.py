"""generate_sprites_v3.py — numpy 像素位移生成不同姿势"""

import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image

REF = '.reasonix/attachments/clipboard-20260627-092305.556221-000001.webp'
OUT = 'sprites'
SIZE = 160

def load_character():
    img = Image.open(REF).convert('RGBA')
    arr = np.array(img, dtype=np.uint8)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    
    # 标记深色像素（黑色背景）
    dark = (r < 30) & (g < 30) & (b < 30)
    
    # 从四角 flood fill 标记外部黑色背景
    h, w = arr.shape[:2]
    from collections import deque
    outside = np.zeros((h, w), dtype=bool)
    q = deque()
    for corner in [(0,0), (0,w-1), (h-1,0), (h-1,w-1)]:
        if dark[corner]:
            q.append(corner)
            outside[corner] = True
    
    while q:
        y, x = q.popleft()
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                if dark[ny, nx] and not outside[ny, nx]:
                    outside[ny, nx] = True
                    q.append((ny, nx))
    
    # 外部黑色背景 → 透明
    a[outside] = 0
    
    img = Image.fromarray(arr, 'RGBA')
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    scale = 110 / h
    return img.resize((int(w * scale), 110), Image.LANCZOS)

def warp_image(img, dx_map, dy_map):
    """
    用位移图变形图像。
    dx_map, dy_map: (h, w) 形状, 每个像素的 x/y 偏移
    """
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    
    # 生成源坐标网格
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    
    # 目标坐标 = 源坐标 + 位移
    src_x = x_coords + dx_map
    src_y = y_coords + dy_map
    
    # 裁剪到图像边界
    src_x = np.clip(src_x, 0, w - 1)
    src_y = np.clip(src_y, 0, h - 1)
    
    # 双线性插值采样
    x0 = np.floor(src_x).astype(int)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y0 = np.floor(src_y).astype(int)
    y1 = np.clip(y0 + 1, 0, h - 1)
    
    fx = src_x - x0
    fy = src_y - y0
    
    # 四个角的像素值
    p00 = arr[y0, x0]
    p10 = arr[y0, x1]
    p01 = arr[y1, x0]
    p11 = arr[y1, x1]
    
    # 双线性插值
    for c in range(4):
        arr[:,:,c] = (
            (1 - fy) * (1 - fx) * p00[:,:,c] +
            (1 - fy) * fx * p10[:,:,c] +
            fy * (1 - fx) * p01[:,:,c] +
            fy * fx * p11[:,:,c]
        )
    
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')

def make_displacement(w, h, func):
    """生成位移场: func(norm_y, norm_x) -> (dx, dy)"""
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    ny = y_coords / max(h - 1, 1)
    nx = x_coords / max(w - 1, 1)
    return func(ny, nx)

def to_canvas(img, size=SIZE):
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    iw, ih = img.size
    cx = (size - iw) // 2
    cy = (size - ih) // 2
    canvas.paste(img, (cx, cy), img)
    return canvas

def clean_alpha(img):
    """二值化 alpha：消除半透明边缘"""
    arr = np.array(img, dtype=np.uint8)
    alpha = arr[:,:,3]
    # alpha < 128 → 0, alpha >= 128 → 255
    arr[:,:,3] = np.where(alpha >= 128, 255, 0)
    # 把透明像素的 RGB 也清零，避免压缩伪影
    mask = arr[:,:,3] == 0
    arr[mask, 0:3] = 0
    return Image.fromarray(arr, 'RGBA')

def save(img, name):
    img = clean_alpha(img)
    path = os.path.join(OUT, name)
    img.save(path)
    print(f'  {name}')

# ════════════════════════════════════

def generate():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.png'):
            os.remove(os.path.join(OUT, f))
    
    base = load_character()
    w, h = base.size
    print(f'Base: {base.size}')
    
    # ── idle (4帧: 轻微呼吸) ──
    for f in range(4):
        phase = f / 4 * math.pi * 2
        amp = np.sin(phase + 0.7)  # 偏移避免 sin(0)=sin(π)=0
        dx, dy = make_displacement(w, h, lambda ny, nx: (
            0,
            np.sin(ny * math.pi) * amp * 1.5
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'idle_{f}.png')
    
    # ── walk (6帧: 左右倾斜+弹跳) ──
    for f in range(6):
        phase = f / 6 * math.pi * 2
        lean = np.sin(phase) * 7 + np.cos(phase) * 2
        bounce = np.abs(np.sin(phase) * 3 + np.cos(phase * 2) * 2)
        dx, dy = make_displacement(w, h, lambda ny, nx, l=lean, b=bounce: (
            l * ny * 1.8,
            b * (1 - np.abs(ny * 2 - 1))  # 中间弹跳最多
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'walk_{f}.png')
    
    # ── sleep (2帧: 压缩) ──
    for f in range(2):
        phase = f / 2 * math.pi
        amp = 0.3 + np.sin(phase) * 0.3
        dx, dy = make_displacement(w, h, lambda ny, nx, a=amp: (
            0,
            ny * 8 * a
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'sleep_{f}.png')
    
    # ── happy_jump (3帧: 上跳拉伸) ──
    for f, amp in enumerate([0.3, 1.0, 0.6]):
        dx, dy = make_displacement(w, h, lambda ny, nx, a=amp: (
            0,
            -ny * 5 * a
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'happy_jump_{f}.png')
    
    # ── happy_land (1帧: 压扁) ──
    dx, dy = make_displacement(w, h, lambda ny, nx: (
        0,
        (1 - np.abs(ny * 2 - 1)) * 7  # 上下向中间挤
    ))
    img = warp_image(base, dx, dy)
    save(to_canvas(img), 'happy_land_0.png')
    
    # ── sad (2帧: 下垂前倾) ──
    for f in range(2):
        amp = 0.6 + f * 0.4
        dx, dy = make_displacement(w, h, lambda ny, nx, a=amp: (
            (nx - 0.5) * 3 * a,
            ny * 6 * a
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'sad_{f}.png')
    
    # ── surprised (2帧: 膨胀) ──
    for f in range(2):
        amp = 0.5 + f * 0.5
        dx, dy = make_displacement(w, h, lambda ny, nx, a=amp: (
            (nx - 0.5) * 5 * a,
            (ny - 0.5) * 6 * a
        ))
        img = warp_image(base, dx, dy)
        save(to_canvas(img), f'surprised_{f}.png')
    
    count = len([f for f in os.listdir(OUT) if f.endswith('.png')])
    print(f'\nDone! {count} sprites')

if __name__ == '__main__':
    generate()
