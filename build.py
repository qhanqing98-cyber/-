# build.py — 打包桌宠为单文件 exe
import os
import PyInstaller.__main__

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)

# 自动扫描词库文件（支持中文文件名）
word_files = []
for f in os.listdir('.'):
    if f.startswith('words_') and f.endswith('.json') and f != 'words_index.json':
        word_files.append(f)
word_files.sort()

# 构建 --add-data 参数
add_data = []
add_data.append('gifs' + os.pathsep + 'gifs')
for wf in word_files:
    if os.path.exists(wf):
        add_data.append(wf + os.pathsep + '.')

args = [
    '--onefile',
    '--noconsole',
    '--name', 'DeskPet',
    '--clean',
    '--noconfirm',
]
for ad in add_data:
    args.append('--add-data')
    args.append(ad)

args.append('main.py')

print('Word files:', word_files)
print('Add-data:', add_data)
print('Running PyInstaller...')
PyInstaller.__main__.run(args)
