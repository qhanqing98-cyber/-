"""generate_sprites_v2.py — 用网格变形生成不同姿势的精灵图"""

import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image

REF = '.reasonix/attachments/clipboard-20260626-232628.559034-000001.webp'
OUT = 'sprites'
SIZE = 160

def load_character():
    """加载参考图，去白底，缩放到合适大小"""
    img = Image.open(REF).convert('RGBA')
    arr = np.array(img, dtype=np.uint8)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    white = (r > 235) & (g > 235) & (b > 235)
    a[white] = 0
    img = Image.fromarray(arr, 'RGBA')
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    # 缩放到约 110px 高
    w, h = img.size
    scale = 110 / h
    return img.resize((int(w * scale), 110), Image.LANCZOS)

def mesh_warp(img, grid_rows=5, grid_cols=4, displacement_map=None):
    """
    用 PIL MESH 变形图像。
    displacement_map: (grid_rows, grid_cols, 2) 每个控制点的 dx, dy
    """
    w, h = img.size
    cell_w = w / (grid_cols - 1)
    cell_h = h / (grid_rows - 1)
    
    # 源网格点
    src_points = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            src_points.append((col * cell_w, row * cell_h))
    
    # 目标网格点（源 + 位移）
    dst_points = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            sx = col * cell_w
            sy = row * cell_h
            if displacement_map is not None:
                dx, dy = displacement_map[row, col]
            else:
                dx, dy = 0, 0
            dst_points.append((sx + dx, sy + dy))
    
    # 构建 quad 列表
    meshes = []
    for row in range(grid_rows - 1):
        for col in range(grid_cols - 1):
            # 四个角: 左上, 右上, 右下, 左下
            tl_src = src_points[row * grid_cols + col]
            tr_src = src_points[row * grid_cols + col + 1]
            br_src = src_points[(row + 1) * grid_cols + col + 1]
            bl_src = src_points[(row + 1) * grid_cols + col]
            
            tl_dst = dst_points[row * grid_cols + col]
            tr_dst = dst_points[row * grid_cols + col + 1]
            br_dst = dst_points[(row + 1) * grid_cols + col + 1]
            bl_dst = dst_points[(row + 1) * grid_cols + col]
            
            meshes.append((
                (tl_dst, tr_dst, br_dst, bl_dst),  # 目标四边形
                (tl_src, tr_src, br_src, bl_src),  # 源四边形
            ))
    
    # PIL MESH transform
    # 使用 MESH 时第二个参数是 (width, height) 的倍数用于目标尺寸
    return img.transform((w, h), Image.MESH, meshes, Image.BILINEAR, fillcolor=0)

def make_displacement(grid_rows, grid_cols, func):
    """生成位移图: func(row, col) -> (dx, dy)"""
    disp = np.zeros((grid_rows, grid_cols, 2), dtype=np.float32)
    for r in range(grid_rows):
        for c in range(grid_cols):
            # 归一化坐标 (0~1)
            ny = r / (grid_rows - 1)
            nx = c / (grid_cols - 1)
            disp[r, c] = func(ny, nx)
    return disp

def to_canvas(img, size=SIZE):
    """放到 SIZE×SIZE 透明画布中央"""
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    iw, ih = img.size
    cx = (size - iw) // 2
    cy = (size - ih) // 2
    canvas.paste(img, (cx, cy), img)
    return canvas

def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path)
    print(f'  {name}')

# ─── 各种姿势的位移函数 ───

def idle_bob(ny, nx):
    """呼吸：上下轻微浮动"""
    return (0, math.sin(ny * math.pi) * 2)

def walk_lean(phase, ny, nx):
    """走路：左右倾斜身体"""
    lean = math.sin(phase) * 5
    # 身体下部比上部倾斜更多
    return (lean * ny * 1.5, math.sin(phase * 2 + ny) * 2)

def sleep_squish(ny, nx):
    """睡觉：整体压缩下垂"""
    return (0, ny * 6 + math.sin(nx * math.pi) * 2)

def happy_stretch(ny, nx):
    """开心：纵向拉伸"""
    return (0, -ny * 4)

def sad_droop(ny, nx):
    """伤心：整体下沉，上部向前倾"""
    return (nx * 3 - 1.5, ny * 5)

def surprised_expand(ny, nx):
    """惊吓：向外膨胀"""
    cx = 0.5
    cy = 0.5
    dx = (nx - cx) * 4
    dy = (ny - cy) * 5
    return (dx, dy)

# ════════════════════════════════════

def generate():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.png'):
            os.remove(os.path.join(OUT, f))
    
    base = load_character()
    w, h = base.size
    print(f'Base: {base.size}')
    
    GR, GC = 6, 5  # 网格密度
    
    # ── idle (4帧: 呼吸) ──
    for f in range(4):
        phase = f / 4.0 * math.pi * 2
        amp = 0.5 + math.sin(phase) * 0.5  # 0~1 渐变
        disp = make_displacement(GR, GC, lambda ny, nx: (
            idle_bob(ny, nx)[0] * amp,
            idle_bob(ny, nx)[1] * amp
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'idle_{f}.png')
    
    # ── walk (6帧: 交替倾斜+弹跳) ──
    for f in range(6):
        phase = f / 6.0 * math.pi * 2
        # 左右倾斜
        lean = math.sin(phase) * 6
        # 上下弹跳
        bounce = abs(math.sin(phase)) * 3
        disp = make_displacement(GR, GC, lambda ny, nx, l=lean, b=bounce: (
            l * ny * 1.8,
            b * (1 - abs(ny - 0.5) * 2) * 0.8  # 身体中部弹跳最多
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'walk_{f}.png')
    
    # ── sleep (2帧: 压缩下垂) ──
    for f in range(2):
        phase = f / 2.0 * math.pi
        amp = 0.5 + math.sin(phase) * 0.5
        disp = make_displacement(GR, GC, lambda ny, nx, a=amp: (
            sleep_squish(ny, nx)[0] * a,
            sleep_squish(ny, nx)[1] * (0.5 + a * 0.5)
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'sleep_{f}.png')
    
    # ── happy_jump (3帧: 跳起+拉伸) ──
    jumps = [0.3, 1.0, 0.3]
    for f in range(3):
        amp = jumps[f]
        disp = make_displacement(GR, GC, lambda ny, nx, a=amp: (
            happy_stretch(ny, nx)[0] * a,
            happy_stretch(ny, nx)[1] * a
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'happy_jump_{f}.png')
    
    # ── happy_land (1帧: 压扁落地) ──
    disp = make_displacement(GR, GC, lambda ny, nx: (
        0, (0.5 - abs(ny - 0.5)) * 6  # 中间向外挤
    ))
    img = mesh_warp(base, GR, GC, disp)
    save(to_canvas(img), 'happy_land_0.png')
    
    # ── sad (2帧: 下垂) ──
    for f in range(2):
        amp = 0.6 + f * 0.4
        disp = make_displacement(GR, GC, lambda ny, nx, a=amp: (
            sad_droop(ny, nx)[0] * a,
            sad_droop(ny, nx)[1] * a
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'sad_{f}.png')
    
    # ── surprised (2帧: 膨胀) ──
    for f in range(2):
        amp = 0.5 + f * 0.5
        disp = make_displacement(GR, GC, lambda ny, nx, a=amp: (
            surprised_expand(ny, nx)[0] * a,
            surprised_expand(ny, nx)[1] * a
        ))
        img = mesh_warp(base, GR, GC, disp)
        save(to_canvas(img), f'surprised_{f}.png')
    
    count = len([f for f in os.listdir(OUT) if f.endswith('.png')])
    print(f'\nDone! {count} sprites')

if __name__ == '__main__':
    generate()
