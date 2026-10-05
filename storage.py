"""共用存档工具：先写临时文件，再替换目标；失败时保留旧数据。"""

import json
import logging
import math
import os
from pathlib import Path
import shutil
import tempfile
import time

log = logging.getLogger('deskpet')


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, suffix='.tmp',
                                         delete=False) as stream:
            temp_path = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        return True
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def backup_corrupt(path):
    """复制损坏文件供恢复；备份失败则抛出异常，调用者不能覆盖原文件。"""
    path = Path(path)
    target = path.with_name(f'{path.name}.{time.time_ns()}.corrupt.bak')
    shutil.copy2(path, target)
    log.warning('损坏文件已备份：%s', target)
    return target


def finite_number(value, default, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        if not math.isfinite(value):
            return default
    except OverflowError:
        return default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value
