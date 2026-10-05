"""运行模式只决定显示和提醒；不处理窗口或绘制。"""
from datetime import datetime
import json
import os
import time
import math

from config import get_data_path
from storage import backup_corrupt, finite_number, log, write_json_atomic


class RuntimeModes:
    def __init__(self, path=None, now=None):
        self.path = path or os.path.join(get_data_path(), 'settings.json')
        self.hidden_by_user = False  # 每次启动可见，避免重启后找不到宠物。
        self.quiet = False
        self.auto_hide_fullscreen = False
        self.pause_until = 0.0
        self.muted_date = ''
        self.fullscreen = False
        self.recovery_available = True  # 运行能力，不属于用户偏好，不写入设置。
        self._show_over_fullscreen = False
        self.last_error = ''
        self._blocked = False
        self._saved_settings = None
        self.now = time.time() if now is None else now
        self._load()

    @property
    def visible(self):
        if not self.recovery_available:
            return True
        return not (self.hidden_by_user or (self.auto_hide_fullscreen and self.fullscreen
                                           and not self._show_over_fullscreen))

    @property
    def learning_paused(self):
        today = datetime.fromtimestamp(self.now).date().isoformat()
        return (not self.visible or self.fullscreen or self.quiet or self.pause_until > self.now
                or self.muted_date == today)

    def refresh(self, fullscreen=None, now=None):
        self.now = time.time() if now is None else now
        if fullscreen is not None:
            self.fullscreen = bool(fullscreen)
            if not self.fullscreen:
                self._show_over_fullscreen = False

    def show(self):
        self.hidden_by_user = False
        self._show_over_fullscreen = True

    def apply_action(self, action):
        """返回是否处理了动作；改变设置的动作立即保存。"""
        if action == 'toggle_visibility':
            if self.visible:
                self.hidden_by_user = True
            else:
                self.show()
            return True
        if action == 'toggle_quiet':
            self.quiet = not self.quiet
        elif action == 'pause_30':
            self.pause_until = self.now + 30 * 60
        elif action == 'pause_today':
            self.muted_date = datetime.fromtimestamp(self.now).date().isoformat()
        elif action == 'resume_learning':
            self.quiet = False
            self.pause_until = 0.0
            self.muted_date = ''
        elif action == 'toggle_fullscreen':
            self.auto_hide_fullscreen = not self.auto_hide_fullscreen
        else:
            return False
        self.save()
        return True

    def snapshot(self):
        """托盘拿到普通字典，保持其对业务模型的依赖很小。"""
        return {'visible': self.visible, 'quiet': self.quiet,
                'learning_paused': self.learning_paused,
                'auto_hide_fullscreen': self.auto_hide_fullscreen,
                'paused_30': self.pause_until > self.now,
                'paused_today': self.muted_date == datetime.fromtimestamp(self.now).date().isoformat()}

    def status_text(self):
        """给悬停面板显示实际暂停原因，分钟变化时才需要重新绘制。"""
        if self.quiet:
            return '安静中'
        if self.muted_date == datetime.fromtimestamp(self.now).date().isoformat():
            return '今日暂停'
        if self.pause_until > self.now:
            return f'暂停·{math.ceil((self.pause_until - self.now) / 60)}分钟'
        if self.fullscreen:
            return '全屏暂停'
        return '学习开启'

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding='utf-8') as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError('设置必须是对象')
            for key in ('quiet', 'auto_hide_fullscreen'):
                if key in data and not isinstance(data[key], bool):
                    raise ValueError(f'{key} 必须是布尔值')
            self.quiet = data.get('quiet', False)
            self.auto_hide_fullscreen = data.get('auto_hide_fullscreen', False)
            self.pause_until = finite_number(data.get('pause_until'), 0.0, 0)
            self.muted_date = data.get('muted_date', '')
            if not isinstance(self.muted_date, str):
                raise ValueError('暂停日期必须是字符串')
            if self.muted_date:
                datetime.fromisoformat(self.muted_date)
            self._saved_settings = self._settings()
        except (OSError, ValueError, TypeError):
            self.quiet, self.auto_hide_fullscreen = False, False
            self.pause_until, self.muted_date = 0.0, ''
            self.last_error = '设置读取失败，已使用默认设置'
            log.exception(self.last_error)
            try:
                backup_corrupt(self.path)
            except OSError:
                self._blocked = True

    def _settings(self):
        return {'quiet': self.quiet, 'auto_hide_fullscreen': self.auto_hide_fullscreen,
                'pause_until': self.pause_until, 'muted_date': self.muted_date}

    def save(self):
        if self._blocked:
            self.last_error = '设置备份失败，已禁止覆盖原文件'
            return False
        try:
            settings = self._settings()
            if settings != self._saved_settings:
                write_json_atomic(self.path, settings)
                self._saved_settings = settings
            self.last_error = ''
            return True
        except (OSError, ValueError):
            self.last_error = '设置已生效，但保存失败，稍后重试'
            log.exception(self.last_error)
            return False
