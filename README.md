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

> 对于MacOS，可以安装[BlackHole](https://existential.audio/blackhole/)来只抓系统声音，从而避免通过麦克风收音：
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
> - 真实扬声器 / 耳机  
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
可用 PyInstaller：  

```bash
pip install pyinstaller
pyinstaller -F -w -i SpectraTray.ico --name SpectraTray app.py
```

生成的可执行文件在 dist/ 目录。
