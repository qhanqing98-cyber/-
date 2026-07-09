# pet.py — 宠物状态机与行为逻辑

import random
import math
import json
import os
from config import *

SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'save.json')


class Pet:
    """桌宠本体：状态、行为、交互响应"""

    def __init__(self):
        self.x = DEFAULT_PET_X + WINDOW_WIDTH // 2
        self.y = DEFAULT_PET_Y + WINDOW_HEIGHT // 2
        self.hunger = 80
        self.mood = 80
        self.energy = 80
        self.behavior = B_IDLE
        self.prev_behavior = B_IDLE
        self.direction = 1
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.animation_finished = True
        self.eval_timer = 0
        self.is_hovered = False
        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.happy_timer = 0
        self.surprised_timer = 0
        self.sleep_z_timer = 0
        self.sleep_z_visible = False
        self.min_x = WINDOW_WIDTH // 2
        self.max_x = SCREEN_WIDTH - WINDOW_WIDTH // 2
        self.min_y_scrn = 0
        self.max_y_scrn = SCREEN_HEIGHT - WINDOW_HEIGHT // 2

        self.feedback_items = []

        # 尝试加载存档
        self._load()

    ANIM_FPS = 10  # 精灵图动画帧率（帧/秒）

    # ─── 主更新 ────────────────────────────────

    def update(self, frozen=False, dt=1.0/60):
        """每帧调用，更新状态和位置。frozen=True 时冻结行为（菜单打开时用）"""
        self._decay_states()
        if not frozen:
            self._evaluate_behavior()
            self._execute_behavior()
        self.frame += 1

        # 时间驱动动画帧（不受实际帧率波动影响）
        self.anim_timer += dt
        frame_duration = 1.0 / self.ANIM_FPS
        while self.anim_timer >= frame_duration:
            self.anim_timer -= frame_duration
            self.anim_frame += 1

        self._update_z_effect()
        self._update_feedback()

    def _decay_states(self):
        self.hunger = max(0, self.hunger - HUNGER_DECAY)
        self.mood = max(0, self.mood - MOOD_DECAY)
        if self.behavior == B_WALK:
            self.energy = max(0, self.energy - ENERGY_WALK_DECAY)
        elif self.behavior == B_SLEEP:
            self.energy = min(100, self.energy + ENERGY_SLEEP_GAIN)
        else:
            self.energy = min(100, self.energy + ENERGY_IDLE_GAIN)

    def _evaluate_behavior(self):
        """按固定间隔评估是否切换行为"""
        self.eval_timer += 1
        if self.eval_timer < BEHAVIOR_EVAL_INTERVAL:
            return
        self.eval_timer = 0

        # 非循环动画正在播放时不做切换
        if not self.animation_finished:
            return

        # 优先级-based 行为选择
        new_behavior = self._choose_behavior()
        if new_behavior != self.behavior:
            self.prev_behavior = self.behavior
            self.behavior = new_behavior
            self.frame = 0
            self.anim_frame = 0
            self.anim_timer = 0.0
            self.animation_finished = False

        # 行走时随机换方向
        if self.behavior == B_WALK and random.random() < 0.15:
            self.direction *= -1

    def _choose_behavior(self):
        if self.energy < 20:
            return B_SLEEP
        if self.hunger < 30:
            return B_SAD
        if self.mood < 30:
            return B_SAD
        r = random.random()
        if r < 0.40:
            return B_IDLE
        return B_WALK

    def _execute_behavior(self):
        """执行当前行为的物理逻辑"""
        if self.behavior == B_WALK:
            self.x += WALK_SPEED * self.direction
            self._clamp_position()

        elif self.behavior == B_HAPPY:
            self.happy_timer -= 1
            if self.happy_timer <= 0:
                self._finish_animation()

        elif self.behavior == B_SURPRISED:
            self.surprised_timer -= 1
            if self.surprised_timer <= 0:
                self._finish_animation()

    def _clamp_position(self):
        self.x = max(self.min_x, min(self.max_x, self.x))
        # 到边界转向
        if self.x <= self.min_x:
            self.direction = 1
        elif self.x >= self.max_x:
            self.direction = -1

    def _finish_animation(self):
        self.animation_finished = True
        # 回到空闲
        self.behavior = B_IDLE
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0

    # ─── Z 特效 ────────────────────────────────

    def _update_z_effect(self):
        if self.behavior == B_SLEEP:
            self.sleep_z_timer += 1
            self.sleep_z_visible = (self.sleep_z_timer % 120) < 60
        else:
            self.sleep_z_timer = 0
            self.sleep_z_visible = False

    def _update_feedback(self):
        self.feedback_items = [item for item in self.feedback_items if item['life'] > 0]
        for item in self.feedback_items:
            item['life'] -= 1
            item['y'] -= item['vy']
            item['x'] += item['vx']
            item['alpha'] = item['life'] / item['max_life']

    def add_feedback(self, text, color, count=5):
        for _ in range(count):
            self.feedback_items.append({
                'text': text,
                'color': color,
                'x': (PET_CENTER_X - 30) + (PET_CENTER_X + 30) * (random.random() - 0.5),
                'y': PET_CENTER_Y - 30,
                'vx': (random.random() - 0.5) * 2,
                'vy': 1 + random.random() * 1.5,
                'life': 60 + random.randint(0, 30),
                'max_life': 90,
                'alpha': 1.0,
                'type': 'text'
            })

    def add_particles(self, color, count=8):
        for _ in range(count):
            angle = random.random() * math.pi * 2
            speed = 2 + random.random() * 3
            self.feedback_items.append({
                'color': color,
                'x': PET_CENTER_X,
                'y': PET_CENTER_Y - 20,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed - 2,
                'life': 40 + random.randint(0, 20),
                'max_life': 60,
                'alpha': 1.0,
                'type': 'particle',
                'size': 3 + random.random() * 4
            })

    # ─── 互动 ──────────────────────────────────

    def on_click(self):
        """左键点击"""
        self.mood = min(100, self.mood + CLICK_MOOD_BOOST)
        self.animation_finished = True  # 打断当前动画
        self.behavior = B_HAPPY
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.happy_timer = 30  # 0.5 秒 (30 帧)
        self.animation_finished = False

    def on_feed(self):
        """喂食"""
        self.hunger = min(100, self.hunger + FEED_HUNGER_BOOST)
        self.mood = min(100, self.mood + 3)
        self.add_feedback('\u1F34E', (255, 160, 80), 3)
        self.add_particles((255, 200, 100), 6)

    def on_pet(self):
        """抚摸"""
        self.mood = min(100, self.mood + PET_MOOD_BOOST)
        self.add_feedback('\u2764\uFE0F', (255, 120, 160), 4)
        self.add_particles((255, 150, 200), 8)

    def on_right_click(self):
        """右键 → 惊喜反应"""
        self.animation_finished = True
        self.behavior = B_SURPRISED
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.surprised_timer = 15
        self.animation_finished = False

    # ─── 碰撞检测 ──────────────────────────────

    def hit_test(self, screen_x, screen_y):
        """检测点击 / hover 是否在宠物身上"""
        dx = screen_x - self.x
        dy = screen_y - (self.y - 10)  # 偏移让碰撞区偏上
        return dx * dx + dy * dy <= HIT_RADIUS * HIT_RADIUS

    # ─── 动画名称（供 character.py 用）────────

    def get_anim_name(self):
        if self.behavior == B_HAPPY and self.happy_timer > 20:
            return 'happy_jump'
        elif self.behavior == B_HAPPY:
            return 'happy_land'
        return self.behavior

    # ─── 状态文本（调试用）────────────────────

    def status_string(self):
        return (f"饥饿:{self.hunger:.0f} 心情:{self.mood:.0f} "
                f"精力:{self.energy:.0f} [{self.behavior}]")

    # ─── 存档 ────────────────────────────────

    def save(self):
        """保存状态到文件"""
        data = {
            'x': self.x,
            'y': self.y,
            'hunger': self.hunger,
            'mood': self.mood,
            'energy': self.energy,
            'direction': self.direction,
        }
        try:
            with open(SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load(self):
        """从文件恢复状态"""
        if not os.path.exists(SAVE_FILE):
            return
        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.x = data.get('x', self.x)
            self.y = data.get('y', self.y)
            self.hunger = data.get('hunger', self.hunger)
            self.mood = data.get('mood', self.mood)
            self.energy = data.get('energy', self.energy)
            self.direction = data.get('direction', self.direction)
            self._clamp_position()
        except Exception:
            pass
