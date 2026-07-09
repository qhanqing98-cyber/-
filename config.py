# config.py — 桌宠配置常量

import ctypes
from ctypes import wintypes

# ——— 窗口参数 ———
WINDOW_WIDTH = 450
WINDOW_HEIGHT = 220
TRANSPARENT_COLOR = (255, 0, 255)  # 品红作为透明键
FPS = 60

# ——— 宠物默认位置（屏幕中间偏下） ———
_user32 = ctypes.windll.user32
SCREEN_WIDTH = _user32.GetSystemMetrics(0)
SCREEN_HEIGHT = _user32.GetSystemMetrics(1)

DEFAULT_PET_X = (SCREEN_WIDTH - WINDOW_WIDTH) // 2
DEFAULT_PET_Y = SCREEN_HEIGHT - WINDOW_HEIGHT - 40

# ——— 宠物在窗口内的绘制坐标 ———
PET_CENTER_X = WINDOW_WIDTH // 2          # 110
PET_CENTER_Y = WINDOW_HEIGHT - 80          # 140（留出跳跃空间）

# ——— 鼠标碰撞半径 ———
HIT_RADIUS = 48

# ——— 状态衰减 (每帧 / 60fps) ———
HUNGER_DECAY = 1.0 / 6000    # 每 100 秒 -1
MOOD_DECAY   = 1.0 / 9000    # 每 150 秒 -1
ENERGY_WALK_DECAY = 1.0 / 1800   # 行走每 30 秒 -1
ENERGY_IDLE_GAIN = 1.0 / 120    # 空闲每 2 秒 +1
ENERGY_SLEEP_GAIN = 1.0 / 30    # 睡眠每 0.5 秒 +1

# ——— 互动回复量 ———
CLICK_MOOD_BOOST = 10
FEED_HUNGER_BOOST = 15
PET_MOOD_BOOST = 5

# ——— 行为参数 ———
BEHAVIOR_EVAL_INTERVAL = 180   # 每 180 帧 (~3 秒) 评估一次行为
WALK_SPEED = 1.5               # 像素/帧

# ——— 行为名称 ———
B_IDLE = 'idle'
B_WALK = 'walk'
B_SLEEP = 'sleep'
B_HAPPY = 'happy'
B_SAD = 'sad'
B_SURPRISED = 'surprised'

# ——— 默认角色颜色 ———
BODY_COLOR = (245, 230, 211)       # #F5E6D3 暖奶油色
BELLY_COLOR = (255, 245, 235)      # #FFF5EB 浅肚子
EAR_COLOR = (232, 196, 168)        # #E8C4A8 耳朵
INNER_EAR_COLOR = (245, 200, 180)  # 内耳粉色
EYE_COLOR = (60, 50, 40)           # 深棕眼睛
CHEEK_COLOR = (255, 182, 193)      # #FFB6C1 腮红
NOSE_COLOR = (255, 150, 150)       # 粉鼻子
MOUTH_COLOR = (100, 80, 70)        # 嘴色
WHISKER_COLOR = (180, 170, 160)    # 胡须
SLEEP_Z_COLOR = (200, 180, 255)    # Z 颜色

# ——— 精灵图目录 ———
SPRITES_DIR = 'sprites'

# ——— 单词学习 ———
WORD_INTERVAL = 300  # 每 5 分钟弹出一个单词（单位：秒）
