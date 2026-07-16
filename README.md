# DeskPet 桌宠

Windows 桌面宠物，支持 GIF 动画、状态互动、多单词本学习和单文件 EXE 打包。

## 开发运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

也可以双击 `run_pet.bat`。右键宠物打开菜单；菜单支持方向键和 Enter；单词卡片支持鼠标点击、空格或 Enter 切换。

## 打包

```powershell
.\.venv\Scripts\python build.py
```

生成文件位于 `dist\DeskPet.exe`。首次启动时，内置词库会复制到 EXE 所在目录。
