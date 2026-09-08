# DeskPet 桌宠

Windows 桌面宠物，支持 GIF 动画、状态互动、多单词本学习和单文件 EXE 打包。

## 开发运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

也可以双击 `run_pet.bat`。右键宠物打开菜单；菜单支持方向键和 Enter；单词卡片支持鼠标点击、空格或 Enter 切换。

### 键盘交互

键盘操作要求桌宠窗口持有焦点：**先用鼠标点一下宠物本体**（悬停时会提示"点击桌宠启用键盘操作"），之后即可：

- `F` 喂食 · `P` 摸摸 · `空格` / `Enter` 逗它开心
- `方向键` 或 `WASD` 移动宠物
- `Esc` 退出（菜单打开时先关闭菜单）

## 打包

```powershell
.\.venv\Scripts\python build.py
```

生成文件位于 `dist\DeskPet.exe`。首次启动时，内置词库会复制到 EXE 所在目录。
