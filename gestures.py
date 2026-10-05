"""按下先等待，超过距离阈值才拖动，松开才确认点击。"""
from config import DRAG_THRESHOLD


class DragGesture:
    def __init__(self, threshold=DRAG_THRESHOLD):
        self.threshold = threshold
        self.pending = False
        self.origin = None

    def press(self, pet, x, y):
        self.cancel(pet)
        self.pending = True
        self.origin = x, y
        pet.drag_offset_x, pet.drag_offset_y = x - pet.x, y - pet.y

    def move(self, pet, x, y):
        if not self.pending:
            return
        dx, dy = x - self.origin[0], y - self.origin[1]
        if not pet.is_dragging and dx * dx + dy * dy >= self.threshold ** 2:
            pet.begin_lift()
        if pet.is_dragging:
            pet.x, pet.y = x - pet.drag_offset_x, y - pet.drag_offset_y
            pet._clamp_position()

    def release(self, pet, x, y):
        if not self.pending:
            return False
        self.move(pet, x, y)
        clicked = not pet.is_dragging and pet.hit_test(x, y)
        self.cancel(pet)
        if clicked:
            pet.on_click()
        return clicked

    def cancel(self, pet):
        self.pending = False
        self.origin = None
        if pet.is_dragging:
            pet.end_lift()
