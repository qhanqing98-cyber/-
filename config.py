# config.py — 桌宠配置常量

import os
import sys
import ctypes

# ——— 窗口参数 ———
WINDOW_WIDTH = 450
WINDOW_HEIGHT = 500
FPS = 60
IDLE_FPS = 30
HIDDEN_FPS = 5
AUTOSAVE_INTERVAL = 30
DRAG_THRESHOLD = 8  # 屏幕像素，超过后才判定为拖动。
PET_MARGIN_X = 100
PET_MARGIN_TOP = 140
PET_MARGIN_BOTTOM = 110

# ——— 宠物默认位置（屏幕中间偏下） ———
_user32 = ctypes.windll.user32
try:
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except AttributeError:
    _user32.SetProcessDPIAware()
SCREEN_WIDTH = _user32.GetSystemMetrics(0)
SCREEN_HEIGHT = _user32.GetSystemMetrics(1)

DEFAULT_PET_X = (SCREEN_WIDTH - WINDOW_WIDTH) // 2
DEFAULT_PET_Y = SCREEN_HEIGHT - WINDOW_HEIGHT - 40

# ——— 宠物在窗口内的绘制坐标 ———
PET_CENTER_X = WINDOW_WIDTH // 2
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
KEY_MOVE_SPEED = 240           # 键盘移动速度（像素/秒）

# ——— 行为名称 ———
B_IDLE = 'idle'
B_WALK = 'walk'
B_SLEEP = 'sleep'
B_HAPPY = 'happy'
B_SAD = 'sad'
B_SURPRISED = 'surprised'
B_PETTING = 'petting'
B_LIFT = 'lift'

# ——— 单词学习 ———
WORD_INTERVAL = 150  # 每 150 秒弹出一个单词

# ——— 打包路径支持 ———
def get_resource_path():
    """返回只读资源目录（打包后为 exe 内部，源码模式为项目目录）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_data_path():
    """源码使用项目目录；EXE 使用用户目录，portable.flag 可启用便携模式。"""
    override = os.environ.get('DESKPET_DATA_DIR')
    if override:
        return os.path.abspath(override)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.exists(os.path.join(exe_dir, 'portable.flag')):
            return exe_dir
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'DeskPet')
    return os.path.dirname(os.path.abspath(__file__))


def prepare_data_directory():
    """复制旧 EXE 旁数据，保留原件；仅补齐不存在的文件。"""
    import shutil
    from storage import log
    target = get_data_path()
    os.makedirs(target, exist_ok=True)
    if not getattr(sys, 'frozen', False):
        return
    source = os.path.dirname(sys.executable)
    marker = os.path.join(target, '.legacy_migrated')
    if os.path.abspath(source) == os.path.abspath(target) or os.path.exists(marker):
        return
    try:
        for filename in os.listdir(source):
            if filename in ('save.json', 'words.json', 'settings.json') or (filename.startswith('words_') and filename.endswith('.json')):
                destination = os.path.join(target, filename)
                if not os.path.exists(destination):
                    shutil.copy2(os.path.join(source, filename), destination)
        progress = os.path.join(source, 'progress')
        if os.path.isdir(progress):
            os.makedirs(os.path.join(target, 'progress'), exist_ok=True)
            for filename in os.listdir(progress):
                if filename.endswith('.json'):
                    destination = os.path.join(target, 'progress', filename)
                    if not os.path.exists(destination):
                        shutil.copy2(os.path.join(progress, filename), destination)
        with open(marker, 'w', encoding='utf-8') as stream:
            stream.write('ok')
    except OSError:
        log.exception('旧数据迁移失败，下次启动会重试')
