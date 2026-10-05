# pet.py — 宠物状态机与行为逻辑

import random
import math
import json
import os
from config import (DEFAULT_PET_X, DEFAULT_PET_Y, WINDOW_WIDTH, WINDOW_HEIGHT,
                    PET_CENTER_X, PET_CENTER_Y, SCREEN_WIDTH, SCREEN_HEIGHT,
                    B_IDLE, B_WALK, B_SLEEP, B_HAPPY, B_SAD, B_SURPRISED,
                    B_PETTING, B_LIFT,
                    WORD_INTERVAL, FPS, HUNGER_DECAY, MOOD_DECAY,
                    ENERGY_WALK_DECAY, ENERGY_SLEEP_GAIN, ENERGY_IDLE_GAIN,
                    BEHAVIOR_EVAL_INTERVAL, WALK_SPEED, CLICK_MOOD_BOOST,
                    FEED_HUNGER_BOOST, PET_MOOD_BOOST, HIT_RADIUS, get_data_path)
from desktop import nearest_work_area, movement_bounds
from config import PET_MARGIN_X, PET_MARGIN_TOP, PET_MARGIN_BOTTOM
from storage import write_json_atomic, backup_corrupt, finite_number, log

SAVE_FILE = os.path.join(get_data_path(), 'save.json')


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
        self.animation_elapsed = 0.0
        self.animation_finished = True
        self.eval_timer = 0
        self.is_hovered = False
        self.panel_timer = 0.0  # 键盘交互后状态面板剩余显示秒数
        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.happy_timer = 0
        self.surprised_timer = 0
        self.petting_timer = 0
        self.sleep_z_timer = 0
        self.sleep_z_visible = False

        self.word_timer = 0.0
        self.word_bubble_active = False
        self.reminder_reset_pending = False

        # x/y 表示宠物中心的屏幕坐标，边界按透明窗口内的绘制中心计算。
        # 这样拖拽后整个窗口仍留在屏幕内，不会因为存档位置而“找不到宠物”。
        self.min_x = PET_CENTER_X
        self.max_x = SCREEN_WIDTH - (WINDOW_WIDTH - PET_CENTER_X)
        self.min_y_scrn = PET_CENTER_Y
        self.max_y_scrn = SCREEN_HEIGHT - (WINDOW_HEIGHT - PET_CENTER_Y)

        self.feedback_items = []
        self.last_error = ''
        self._save_blocked = False

        # 单词间隔（默认从配置，可在运行时修改并持久化）
        self.word_interval = WORD_INTERVAL

        # 尝试加载存档
        self._load()

    ANIM_FPS = 10  # 精灵图动画帧率（帧/秒）

    # ─── 主更新 ────────────────────────────────

    def update(self, frozen=False, dt=1.0/60):
        """每帧调用，更新状态和位置。frozen=True 时冻结行为（菜单打开时用）"""
        # 将原先按 60 FPS 调好的数值换算为真实时间，同时限制卡顿后的
        # 单帧补偿，避免打开系统对话框后宠物突然冲出很远。
        dt = max(0.0, min(dt, 0.1))
        frame_scale = dt * FPS
        self._decay_states(frame_scale)
        if not frozen and not self.is_dragging:
            self._evaluate_behavior(dt)
            self._execute_behavior(frame_scale)
        elif self.behavior in (B_HAPPY, B_SURPRISED, B_PETTING):
            # 安静模式和菜单只冻结走动，短时互动仍需正常结束。
            self._execute_behavior(frame_scale)
        self.frame += frame_scale

        # 时间驱动动画帧（不受实际帧率波动影响）
        self.animation_elapsed += dt
        self.anim_timer += dt
        frame_duration = 1.0 / self.ANIM_FPS
        while self.anim_timer >= frame_duration:
            self.anim_timer -= frame_duration
            self.anim_frame += 1

        self._update_z_effect(dt)
        self._update_feedback(frame_scale)
        self._clamp_position()
        # 状态面板计时（键盘交互触发，随时间淡出）
        self.panel_timer = max(0.0, self.panel_timer - dt)

    def show_panel(self, seconds=2.5):
        """键盘交互后短暂显示状态面板（鼠标悬停外的另一种唤出方式）"""
        self.panel_timer = max(self.panel_timer, seconds)

    def _decay_states(self, frame_scale=1.0):
        self.hunger = max(0, self.hunger - HUNGER_DECAY * frame_scale)
        self.mood = max(0, self.mood - MOOD_DECAY * frame_scale)
        if self.behavior == B_WALK:
            self.energy = max(0, self.energy - ENERGY_WALK_DECAY * frame_scale)
        elif self.behavior == B_SLEEP:
            self.energy = min(100, self.energy + ENERGY_SLEEP_GAIN * frame_scale)
        else:
            self.energy = min(100, self.energy + ENERGY_IDLE_GAIN * frame_scale)

    def _evaluate_behavior(self, dt=1.0/60):
        """按固定间隔评估是否切换行为"""
        self.eval_timer += max(dt, 0.0)
        if self.eval_timer < BEHAVIOR_EVAL_INTERVAL / FPS:
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
            self.animation_elapsed = 0.0
            # idle/walk/sleep/sad 都是循环行为，必须继续参与下一轮评估。
            # 只有点击触发的 happy/surprised 属于一次性动画。
            self.animation_finished = True

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

    def _execute_behavior(self, frame_scale=1.0):
        """执行当前行为的物理逻辑"""
        if self.behavior == B_WALK:
            self.x += WALK_SPEED * self.direction * frame_scale
            self._clamp_position()

        elif self.behavior == B_HAPPY:
            self.happy_timer -= frame_scale
            if self.happy_timer <= 0:
                self._finish_animation()

        elif self.behavior == B_SURPRISED:
            self.surprised_timer -= frame_scale
            if self.surprised_timer <= 0:
                self._finish_animation()

        elif self.behavior == B_PETTING:
            self.petting_timer -= frame_scale
            if self.petting_timer <= 0:
                self._finish_animation()

    def _clamp_position(self):
        area = nearest_work_area(self.x, self.y)
        self.min_x, self.min_y_scrn, self.max_x, self.max_y_scrn = movement_bounds(
            self.x, self.y, area, PET_MARGIN_X, PET_MARGIN_TOP, PET_MARGIN_BOTTOM)
        requested_x = self.x
        self.x = max(self.min_x, min(self.max_x, self.x))
        self.y = max(self.min_y_scrn, min(self.max_y_scrn, self.y))
        # 到边界转向
        if requested_x < self.min_x:
            self.direction = 1
        elif requested_x > self.max_x:
            self.direction = -1

    def _finish_animation(self):
        self.animation_finished = True
        # 回到空闲
        self.behavior = B_IDLE
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.animation_elapsed = 0.0

    # ─── Z 特效 ────────────────────────────────

    def _update_z_effect(self, dt=1.0/60):
        if self.behavior == B_SLEEP:
            self.sleep_z_timer += dt
            self.sleep_z_visible = (self.sleep_z_timer % 2.0) < 1.0
        else:
            self.sleep_z_timer = 0
            self.sleep_z_visible = False

    def _update_feedback(self, frame_scale=1.0):
        for item in self.feedback_items:
            item['life'] -= frame_scale
            item['y'] -= item['vy'] * frame_scale
            item['x'] += item['vx'] * frame_scale
            item['alpha'] = max(0.0, item['life'] / item['max_life'])
        self.feedback_items = [item for item in self.feedback_items if item['life'] > 0]

    def add_feedback(self, text, color, count=5):
        for _ in range(count):
            self.feedback_items.append({
                'text': text,
                'color': color,
                'x': PET_CENTER_X + (random.random() - 0.5) * 60,
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
        self.animation_elapsed = 0.0
        self.happy_timer = 60  # 一秒，完整表现开心动作。
        self.animation_finished = False

    def on_feed(self):
        """喂食"""
        self.hunger = min(100, self.hunger + FEED_HUNGER_BOOST)
        self.mood = min(100, self.mood + 3)
        self.add_feedback('\U0001F34E', (255, 160, 80), 3)
        self.add_particles((255, 200, 100), 6)

    def on_pet(self):
        """抚摸"""
        self.mood = min(100, self.mood + PET_MOOD_BOOST)
        self.behavior = B_PETTING
        self.animation_elapsed = 0.0
        self.anim_timer = 0.0
        self.anim_frame = 0
        self.petting_timer = 72
        self.animation_finished = False
        self.add_feedback('\u2764\uFE0F', (255, 120, 160), 4)
        self.add_particles((255, 150, 200), 8)

    def on_right_click(self):
        """右键 → 惊喜反应"""
        self.animation_finished = True
        self.behavior = B_SURPRISED
        self.frame = 0
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.animation_elapsed = 0.0
        self.surprised_timer = 42
        self.animation_finished = False

    def begin_lift(self):
        """拖动开始时切到被提起动作，不增加点击奖励。"""
        self.is_dragging = True
        self.behavior = B_LIFT
        self.animation_elapsed = 0.0
        self.animation_finished = False

    def end_lift(self):
        self.is_dragging = False
        self._finish_animation()
        self.eval_timer = 0.0

    def settle(self):
        """进入安静模式时停止走动，保持休息姿态。"""
        self.is_dragging = False
        self._finish_animation()
        self.eval_timer = 0.0

    def recenter(self, screen_x, screen_y):
        left, top, right, bottom = nearest_work_area(screen_x, screen_y)
        self.x, self.y = (left + right) / 2, (top + bottom) / 2
        self._clamp_position()

    # ─── 碰撞检测 ──────────────────────────────

    def hit_test(self, screen_x, screen_y):
        """检测点击 / hover 是否在宠物身上"""
        dx = screen_x - self.x
        dy = screen_y - (self.y - 10)  # 偏移让碰撞区偏上
        return dx * dx + dy * dy <= HIT_RADIUS * HIT_RADIUS

    # ─── 动画名称（供 character.py 用）────────

    def get_anim_name(self):
        return self.behavior

    # ─── 状态文本（调试用）────────────────────

    def status_string(self):
        return (f"饥饿:{self.hunger:.0f} 心情:{self.mood:.0f} "
                f"精力:{self.energy:.0f} [{self.behavior}]")

    # ─── 存档 ────────────────────────────────

    def save(self):
        """保存状态到文件"""
        if self._save_blocked:
            self.last_error = '存档备份失败，已禁止覆盖原文件'
            return False
        data = {
            'x': self.x,
            'y': self.y,
            'hunger': self.hunger,
            'mood': self.mood,
            'energy': self.energy,
            'direction': self.direction,
            'word_interval': self.word_interval,
        }
        try:
            write_json_atomic(SAVE_FILE, data)
            self.last_error = ''
            return True
        except (OSError, ValueError):
            self.last_error = '保存宠物状态失败，请检查磁盘空间或权限'
            log.exception(self.last_error)
            return False

    def _load(self):
        """从文件恢复状态"""
        if not os.path.exists(SAVE_FILE):
            return
        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError('存档必须是对象')
            self.x = finite_number(data.get('x'), self.x)
            self.y = finite_number(data.get('y'), self.y)
            for field in ('hunger', 'mood', 'energy'):
                setattr(self, field, finite_number(data.get(field), getattr(self, field), 0, 100))
            self.direction = -1 if data.get('direction') == -1 else 1
            self.word_interval = finite_number(data.get('word_interval'), WORD_INTERVAL, 10, 3600)
            self._clamp_position()
        except (OSError, ValueError, TypeError):
            self.last_error = '存档损坏，已恢复默认状态'
            log.exception(self.last_error)
            try:
                backup_corrupt(SAVE_FILE)
            except OSError:
                self._save_blocked = True
