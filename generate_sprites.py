"""generate_sprites.py — 从当前Q版猫渲染精灵图到 sprites/ 目录"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from PIL import Image
from config import *
from pet import Pet
import character

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), SPRITES_DIR)
SIZE = 160  # 精灵图尺寸（正方形）

def make_surface():
    """创建透明画布"""
    return pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)

def render_pet(pet, surf):
    """把宠物画到 surf 上，居中"""
    surf.fill((0, 0, 0, 0))
    old_cx = PET_CENTER_X
    old_cy = PET_CENTER_Y
    # 临时改 PET_CENTER 居中到 surf 中心
    import config
    config.PET_CENTER_X = SIZE // 2
    config.PET_CENTER_Y = SIZE // 2 + 10  # 略偏下留空间
    character.draw_pet(surf, pet)
    config.PET_CENTER_X = old_cx
    config.PET_CENTER_Y = old_cy

def save_frame(surf, name):
    """将 pygame surface 存为 PNG"""
    data = pygame.image.tostring(surf, 'RGBA')
    img = Image.frombytes('RGBA', surf.get_size(), data)
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print(f'  {name}')

def generate():
    pygame.init()
    pygame.display.set_mode((1, 1))  # 隐藏窗口
    character.load_sprites()
    os.makedirs(OUT_DIR, exist_ok=True)

    pet = Pet()
    surf = make_surface()

    # ── idle (4帧: 呼吸浮动) ──
    pet.behavior = B_IDLE
    pet.animation_finished = True
    for f in range(4):
        pet.frame = f * 15  # 不同呼吸相位
        render_pet(pet, surf)
        save_frame(surf, f'idle_{f}.png')

    # ── walk (6帧: 走路循环) ──
    pet.behavior = B_WALK
    for f in range(6):
        pet.frame = f * 5
        pet.direction = 1
        render_pet(pet, surf)
        save_frame(surf, f'walk_{f}.png')

    # ── sleep (2帧: 呼吸) ──
    pet.behavior = B_SLEEP
    pet.sleep_z_visible = True
    for f in range(2):
        pet.frame = f * 90
        render_pet(pet, surf)
        save_frame(surf, f'sleep_{f}.png')

    # ── happy_jump (3帧: 跳起) ──
    pet.behavior = B_HAPPY
    pet.happy_timer = 30
    pet.animation_finished = False
    for f in range(3):
        pet.frame = f * 8
        pet.happy_timer = 30 - f * 8
        render_pet(pet, surf)
        save_frame(surf, f'happy_jump_{f}.png')

    # ── happy_land (1帧: 落地) ──
    pet.behavior = B_HAPPY
    pet.frame = 28
    pet.happy_timer = 2
    render_pet(pet, surf)
    save_frame(surf, 'happy_land_0.png')

    # ── sad (2帧) ──
    pet.behavior = B_SAD
    for f in range(2):
        pet.frame = f * 60
        render_pet(pet, surf)
        save_frame(surf, f'sad_{f}.png')

    # ── surprised (2帧) ──
    pet.behavior = B_SURPRISED
    pet.surprised_timer = 15
    for f in range(2):
        pet.frame = f * 6
        pet.surprised_timer = 15 - f * 6
        render_pet(pet, surf)
        save_frame(surf, f'surprised_{f}.png')

    pygame.quit()
    print(f'\nDone! {len(os.listdir(OUT_DIR))} sprites in {OUT_DIR}')

if __name__ == '__main__':
    generate()
