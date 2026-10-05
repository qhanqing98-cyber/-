"""提醒计时独立于动画帧率；长时间阻塞或唤醒后重新等待。"""
import time


class ReminderTimer:
    def __init__(self, now=None):
        self.last = time.monotonic() if now is None else now
        self.was_eligible = None

    def update(self, pet, has_words, paused=False, menu_active=False, now=None):
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.last)
        self.last = now
        # 睡眠唤醒、长卡顿和模态对话框返回后不立即弹出或连发卡片。
        reset = elapsed >= 5.0 or pet.reminder_reset_pending
        if reset:
            pet.word_timer = 0.0
            pet.word_bubble_active = False
            pet.reminder_reset_pending = False
        eligible = has_words and not paused and not menu_active and not pet.word_bubble_active
        if eligible and self.was_eligible is False:
            pet.word_timer = 0.0
            reset = True
        self.was_eligible = eligible
        if eligible and not reset:
            pet.word_timer += elapsed
            if pet.word_timer >= pet.word_interval:
                pet.word_bubble_active = True
                pet.word_timer = 0.0
                self.was_eligible = False
                return True
        return False
