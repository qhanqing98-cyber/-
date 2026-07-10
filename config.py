# config.py — 桌宠配置常量

import os
import sys
import ctypes
from ctypes import wintypes

# ——— 窗口参数 ———
WINDOW_WIDTH = 450
WINDOW_HEIGHT = 500
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
PET_CENTER_Y = WINDOW_HEIGHT - 150          # 留出下半部分空间（大 GIF 角色）

# ——— 鼠标碰撞半径 ———
HIT_RADIUS = 70

# ——— 状态衰减 (每帧 / 60fps) ———
HUNGER_DECAY = 1.0 / 600     # 每 10 秒 -1
MOOD_DECAY   = 1.0 / 1200    # 每 20 秒 -1
ENERGY_WALK_DECAY = 1.0 / 300    # 行走每 5 秒 -1
ENERGY_IDLE_GAIN = 1.0 / 60      # 空闲每 1 秒 +1
ENERGY_SLEEP_GAIN = 1.0 / 15     # 睡眠每 0.25 秒 +1

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

# ——— 单词学习 ———
WORD_INTERVAL = 150  # 每 150 秒弹出一个单词

# ——— 打包路径支持 ———
def get_resource_path():
    """返回只读资源目录（打包后为 exe 内部，源码模式为项目目录）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_data_path():
    """返回可写数据目录（始终为 exe 所在目录，用户存档/单词本放在此处）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))