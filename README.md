# SpectraTray（声谱托盘）

<p align="center"><img src="https://github.com/user-attachments/assets/042bf821-21ff-4e63-b08c-f3b27b86502f" width="400"></p>

一个运行在 Windows 系统托盘的实时“系统声音频谱”小工具：抓取系统正在播放的声音（Loopback），将频谱分成 8 个频段，用彩色柱状图在托盘图标里实时显示。

- 网站：https://xfxuezhang.cn

## 功能特性

- ✅ 抓取系统回放声音（Loopback），不需要外接麦克风
- ✅ 8 频段实时频谱（更能反映高音/瞬态变化）
- ✅ 托盘图标 64×64 彩色柱状显示
- ✅ 右键菜单：
  - 背景色：透明 / 白色 / 黑色
  - 灵敏度：高 / 中 / 低
  - 版本号显示
- ✅ 双击托盘图标打开网站（xfxuezhang.cn）


> ​下载链接(github,推荐)：https://github.com/1061700625/SpectraTray/releases  
> 下载链接(lanzou)：https://xfxuezhang.lanzouv.com/iDJoE3dryb3c

​

## 环境要求

- Windows 10/11
- MacOS
- Python 3.8+


## 安装依赖

```bash
conda create -n tray python=3.10 -y
conda activate tray

# For windows
pip install numpy pillow pystray SoundCard

# For macos
pip install -i https://pypi.org/simple pystray pillow numpy SoundCard pyobjc
```

> 对于MacOS，可以安装[BlackHole 2ch](https://existential.audio/blackhole/)或[BlackHole 16ch](https://www.filmagepro.com/downloads/BlackHole.pkg)来只抓系统声音，从而避免通过麦克风收音([教程](https://obsproject.com/forum/resources/mac-desktop-audio-using-blackhole.1191/))：
> 
> 1、安装blackhole：
> ```bash
> brew install blackhole-2ch
> ```
> 
> 2、打开 音频 MIDI 设置
> 
> 3、点左下角 + → 创建多输出设备
> 
> 4、勾选：  
> - MacBook扬声器 (注意得排第一个) 
> - BlackHole 2ch
> 
> 5、右击，选择“将此设备用于声音输出”

## 运行

```bash
python app.py
```

运行后会出现托盘图标，右键可切换背景色和灵敏度。

## 常见问题

**1) 提示 data discontinuity in recording**  

这是录音数据存在不连续的警告，通常不影响实时显示；本项目已默认屏蔽该警告。

**2) 抓不到声音？**  

如果播放器使用了独占模式（例如某些 WASAPI Exclusive/ASIO），可能会绕开系统混音，导致 Loopback 取不到数据。请关闭独占模式或改用普通输出模式。

## 打包成 EXE
可用 PyInstaller。

```bash
pip install pyinstaller

pyinstaller -F -w -i SpectraTray.ico --name SpectraTray app.py
```

生成的可执行文件在 dist/ 目录。

## 打包成 app
可用 py2app。

1、生成配置文件。

```bash
py2applet --make-setup app.py
```

2、编辑setup.py。

```python
from setuptools import setup

APP = ["app.py"]

OPTIONS = {
    # 托盘程序不需要终端窗口
    "argv_emulation": False,

    "iconfile": "SpectraTray.ico",

    # 关键：定制 Info.plist（官方文档：Tweaking your Info.plist）
    "plist": {
        "CFBundleName": "SpectraTray",
        "CFBundleDisplayName": "SpectraTray",
        "CFBundleIdentifier": "com.xfxuezhang.spectratray",

        # 托盘应用常用：不在 Dock 显示图标（仅菜单栏/托盘）
        "LSUIElement": True,

        # 麦克风用途说明：没有它 macOS 可能不会弹权限窗/直接拒绝
        "NSMicrophoneUsageDescription": "用于采集音频以显示频谱（不保存、不上传）。",
    },
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

3、继续执行。

```bash
rm -rf build dist

python setup.py py2app                      

/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 用于采集 音频以显示频谱（不保存、不上传）"  dist/SpectraTray.app/Contents/Info.plist

mkdir -p dist/SpectraTray.app/Contents/Frameworks/

cp /opt/homebrew/opt/libffi/lib/libffi.8.dylib dist/SpectraTray.app/Contents/Frameworks/

install_name_tool -id @rpath/libffi.8.dylib dist/SpectraTray.app/Contents/Frameworks/libffi.8.dylib

codesign --force --deep --sign - dist/SpectraTray.app
```
生成的可执行文件在 dist/ 目录。



