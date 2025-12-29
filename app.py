# -*- coding: utf-8 -*-
"""
SpectraTray（声谱托盘）
=====================
一个 Windows 系统托盘频谱显示小工具：

核心思路
- 用 soundcard 把“默认扬声器输出”以 loopback 的方式当成输入录下来（即抓系统正在播放的声音）
- 每次取一段音频做 FFT（快速傅里叶变换），得到频谱幅度
- 把频率轴按对数方式分成 8 个频段（更符合人耳听感：低频更密、高频更稀）
- 每个频段用“峰值跟踪 + 动态范围(db_range)”做归一化，映射成 0~10 档
- 用 PIL 动态生成一个 64x64 的托盘图标：8 根彩色柱，且只画“亮”的部分（不画灰色关灯部分）
- pystray 提供托盘图标、右键菜单、以及“默认菜单项”用于实现双击打开网站

右键菜单
- 打开官网
- 背景色：透明 / 白色 / 黑色
- 灵敏度：高 / 中 / 低（本质是动态范围 db_range）
- 版本号显示
- 退出
"""

import time
import threading
import math
import warnings
import webbrowser
import numpy as np
import soundcard as sc
from PIL import Image, ImageDraw
import pystray
import sys


# =========================
# 应用信息/常量配置
# =========================

# 中英文名（用于托盘标题）
APP_NAME_CN = "声谱托盘"
APP_NAME_EN = "SpectraTray"
APP_NAME = f"{APP_NAME_CN} / {APP_NAME_EN}"

# 版本号（用于菜单显示/托盘标题）
__version__ = "0.0.1"

# 双击托盘图标后打开的网页
WEBSITE_URL = "https://github.com/1061700625/SpectraTray"

# 托盘图标绘制尺寸（最终系统可能会缩放到 16/24/32 之类显示）
ICON_SIZE = 64

# 8 个频段的配色（低频 -> 高频），刻意避开“纯绿”以减少看不清的问题
BAND_COLORS = [
    (255,  70,  70),  # 红
    (255, 150,  60),  # 橙
    (255, 225,  80),  # 黄
    (255,  90, 170),  # 粉
    (205,  90, 255),  # 紫
    (120, 120, 255),  # 靛
    ( 80, 170, 255),  # 蓝
    ( 70, 235, 255),  # 青（偏蓝青）
]


# =========================
# 通用小工具函数
# =========================

def clamp(x, a, b):
    """把 x 限制在 [a, b]，防止出现越界值。"""
    return a if x < a else (b if x > b else x)


# =========================
# 图标绘制：把“频段档位”画成托盘图标
# =========================

def make_spectrum_icon(levels, max_level, bg_mode="black", size=ICON_SIZE):
    """
    根据每个频段的档位 levels 生成托盘图标（PIL Image）。

    参数
    - levels: List[int]
        每个频段的“亮格数”（0..max_level），例如 8 个频段则长度为 8。
    - max_level: int
        总档位数（默认 10），决定一根柱子最多分多少格。
    - bg_mode: str
        背景模式：'transparent' / 'white' / 'black'
    - size: int
        图标画布尺寸（默认 64）

    绘制策略
    - 先画背景（可选，透明则不画底）
    - 计算 8 根柱子的 x 位置、每一格的高度
    - 对每个频段：只画从底往上的 lv 个亮格（不画“未点亮”的上半部分）
    """
    # RGBA 透明画布（alpha=0 表示完全透明）
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 外边距，避免图形贴边
    pad = 2

    # -------------------------
    # 画背景（可选）
    # -------------------------
    if bg_mode == "transparent":
        bg = None  # 透明背景：不画底
    elif bg_mode == "white":
        bg = (255, 255, 255, 255)
    else:  # "black"
        bg = (12, 12, 12, 255)

    if bg is not None:
        # 画圆角矩形底框（radius 越大越圆）
        d.rounded_rectangle(
            [pad, pad, size - pad - 1, size - pad - 1],
            radius=4,
            fill=bg
        )

    # -------------------------
    # 计算柱状布局
    # -------------------------
    n_bands = len(levels)  # 频段数量（一般是 8）
    gap = 1                # 每根柱子之间的间隔（像素）

    # 每根柱子的宽度：根据画布宽度均分，至少 2px，避免太细
    bar_w = max(2, (size - 2 * (pad + 2) - gap * (n_bands - 1)) // n_bands)

    # 内部绘制区域（相对背景再缩一点，留出呼吸感）
    inner_l = pad + 2
    inner_r = size - pad - 3
    inner_t = pad + 2
    inner_b = size - pad - 3

    # 每一“格”之间的垂直间距
    seg_gap = 1

    # 一根柱子的可用高度
    total_h = inner_b - inner_t

    # 每一格的高度（像素）：把总高度按 max_level 分成 max_level 段
    seg_h = max(1, (total_h - seg_gap * (max_level - 1)) // max_level)

    # -------------------------
    # 逐频段绘制
    # -------------------------
    for bi in range(n_bands):
        # 该频段柱子的 x 坐标范围
        x0 = inner_l + bi * (bar_w + gap)
        x1 = min(x0 + bar_w, inner_r)

        # 该频段对应的颜色（循环取色，避免越界）
        col = BAND_COLORS[bi % len(BAND_COLORS)]
        on = (col[0], col[1], col[2], 255)

        # 当前频段亮几格（0..max_level）
        lv = int(levels[bi])
        lv = clamp(lv, 0, max_level)

        # 只画亮的段：si=0 是底部第一格
        for si in range(lv):
            y1 = inner_b - si * (seg_h + seg_gap)
            y0 = y1 - seg_h
            d.rectangle([x0, y0, x1, y1], fill=on)

    return img


# =========================
# 频段切分：把 FFT 的 bin 分配到 8 个频段
# =========================

def build_band_bins(sr, nfft, n_bands=8, fmin=80.0, fmax=16000.0):
    """
    对数分段，把 FFT 频率轴切成 n_bands 段，返回每段对应的 rfft bin 切片范围。

    为什么用对数分段？
    - 人耳对频率的感知接近对数刻度（低频更敏感）
    - 这样分段后低频段更细致，高频段更宽一些，显示更自然

    返回值
    - bins: List[(a,b)]
        其中 a/b 是 rfft 结果数组的索引，表示可以用 mag_db[a:b] 取出该频段的能量。
    """
    # rfft 的频率轴（只包含 0..Nyquist）
    freqs = np.fft.rfftfreq(nfft, d=1.0 / sr)

    # 生成对数分段的边界频率：长度 n_bands+1
    edges = np.logspace(math.log10(fmin), math.log10(fmax), n_bands + 1)

    bins = []
    for i in range(n_bands):
        lo, hi = edges[i], edges[i + 1]

        # 找到落在 [lo, hi) 的 bin 索引
        idx = np.where((freqs >= lo) & (freqs < hi))[0]
        if len(idx) == 0:
            # 该频段没有任何 bin（极端情况下可能发生），用 (0,0) 代表空
            bins.append((0, 0))
        else:
            # b 用开区间，方便切片 mag_db[a:b]
            bins.append((int(idx[0]), int(idx[-1]) + 1))
    return bins

def pick_recording_source(prefer_names=("BlackHole", "Loopback", "VB-Audio", "Soundflower")):
    """
    自动选择“能抓到系统输出”的录音源：
    - Windows：默认扬声器 + include_loopback=True
    - macOS：优先找 BlackHole/Loopback 等虚拟设备；找不到则退回默认麦克风
    返回：(mic, hint_text)
      mic: soundcard microphone object
      hint_text: 用于提示用户的字符串（可能为空）
    """
    plat = sys.platform.lower()

    # ---------- Windows：WASAPI loopback ----------
    if plat.startswith("win"):
        speaker = sc.default_speaker()
        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        return mic, ""

    # ---------- macOS：没有原生 loopback，只能靠虚拟声卡 ----------
    if plat == "darwin":
        mics = sc.all_microphones()
        # 优先匹配虚拟设备
        for key in prefer_names:
            for m in mics:
                if key.lower() in m.name.lower():
                    return m, ""

        # 找不到虚拟设备：退回默认麦克风，但给出提示
        hint = "未检测到 BlackHole/Loopback 虚拟声卡，已退回默认麦克风（无法抓系统输出）"
        return sc.default_microphone(), hint

    # ---------- 其它平台：先简单退回默认麦克风 ----------
    return sc.default_microphone(), "当前平台未实现系统输出抓取，已退回默认麦克风"


# =========================
# 主类：托盘图标 + 菜单 + 后台音频采集线程
# =========================

class TraySpectrumMeter:
    def __init__(self, default_levels=10):
        # 线程同步锁：保护共享状态（菜单修改参数时与 worker 并发）
        self._lock = threading.Lock()

        # 退出事件：worker 循环依靠它停止
        self._stop = threading.Event()

        # 强制重绘：菜单改设置后，让下一帧必定更新图标
        self._force_redraw = threading.Event()

        # -------------------------
        # 显示参数
        # -------------------------
        # 固定档位（不提供菜单切换）
        self.max_level = int(default_levels)

        # 灵敏度选项：本质是动态范围 db_range
        # db_range 越小 => 更灵敏（更容易满格）
        # db_range 越大 => 更不灵敏（更不容易满格）
        self.db_range_choices = [("高灵敏", 45.0), ("中灵敏", 60.0), ("低灵敏", 75.0)]
        self.db_range = 60.0

        # 背景模式选项
        self.bg_modes = [("透明", "transparent"), ("白色", "white"), ("黑色", "black")]
        self.bg_mode = "black"

        # 峰值跟踪衰减（dB/帧）：决定“峰值参考线”下降速度
        # 值越小：峰值下降越慢 -> 不容易一直顶满（更稳）
        self.peak_decay_db = 0.06

        # -------------------------
        # 音频/频谱参数
        # -------------------------
        self.n_bands = 8
        self.nfft = 4096        # FFT 点数：越大频率分辨率越高，但刷新更慢
        self.samplerate = 48000 # 采样率

        # -------------------------
        # 双击判定参数
        # -------------------------
        # 使用 pystray 的 default item 来接收托盘图标“主键点击”
        # 通过时间差判断是否为双击
        self._last_primary_click = 0.0
        self._double_click_gap = 0.35  # 两次点击间隔阈值（秒）

        # --------- 杂音滤除（仅影响显示）---------
        self.denoise_enabled = False
        self.denoise_strength_choices = [("弱", 0.8), ("中", 1.2), ("强", 1.8)]
        self.denoise_alpha = 1.2
        self._learn_noise = threading.Event()   # 触发学习噪声画像
        self._noise_profile = None              # np.ndarray, 线性幅度谱（rfft 长度）
        self._noise_band_db = None              # shape: (n_bands,)
        self.denoise_gate_margin_db = 0.0         # 噪声门
        # --------- 频段统计方式（Max / RMS / P90）---------
        self.band_stat_choices = [
            ("峰值 Max (更跳)", "max"),
            ("能量 RMS (更稳)", "rms"),
            ("分位数 P90 (抗尖峰)", "p90"),
        ]
        self.band_stat = "rms"  # 默认 RMS

        # -------------------------
        # 创建托盘图标对象
        # -------------------------
        self.icon = pystray.Icon(
            name=APP_NAME_EN,
            icon=make_spectrum_icon([0] * self.n_bands, self.get_max_level(), self.get_bg_mode(), ICON_SIZE),
            title=f"{APP_NAME} v{__version__}",
            menu=self._build_menu(),
        )

    # ---------- 线程安全的 getter/setter ----------

    def get_max_level(self):
        """读取总档位数（线程安全）。"""
        with self._lock:
            return self.max_level

    def get_db_range(self):
        """读取动态范围 db_range（线程安全）。"""
        with self._lock:
            return float(self.db_range)

    def _set_db_range(self, r):
        """设置动态范围，并通知 worker 强制重绘（线程安全）。"""
        with self._lock:
            self.db_range = float(r)
        self._force_redraw.set()

    def get_bg_mode(self):
        """读取背景模式（线程安全）。"""
        with self._lock:
            return self.bg_mode

    def _set_bg_mode(self, mode):
        """设置背景模式，并通知 worker 强制重绘（线程安全）。"""
        with self._lock:
            self.bg_mode = str(mode)
        self._force_redraw.set()

    def get_denoise_enabled(self):
        with self._lock:
            return bool(self.denoise_enabled)

    def _set_denoise_enabled(self, v):
        with self._lock: self.denoise_enabled = bool(v)
        self._force_redraw.set()

    def get_denoise_alpha(self):
        with self._lock:
            return float(self.denoise_alpha)

    def _set_denoise_alpha(self, a):
        with self._lock: self.denoise_alpha = float(a)
        self._force_redraw.set()

    def get_band_stat(self):
        with self._lock:
            return str(self.band_stat)

    def _set_band_stat(self, mode):
        with self._lock:
            self.band_stat = str(mode)
        self._force_redraw.set()


    # ---------- 打开网站 / 双击逻辑 ----------

    def _open_website(self):
        """用系统默认浏览器打开项目主页。"""
        try:
            webbrowser.open_new_tab(WEBSITE_URL)
        except Exception:
            # 打开失败时静默处理（不弹窗、不影响托盘主循环）
            pass

    def _on_default_primary_click(self, icon, item):
        """
        用 pystray 的 default item 模拟“托盘双击”：
        - 第一次主键点击：记录时间
        - 第二次在阈值内：认为是双击 -> 打开网站
        """
        now = time.monotonic()  # monotonic 不受系统时间调整影响，更适合算间隔
        if now - self._last_primary_click <= self._double_click_gap:
            self._last_primary_click = 0.0
            self._open_website()
        else:
            self._last_primary_click = now

    def _on_open_website_menu(self, icon, item):
        """右键菜单：打开官网（单次）。"""
        self._open_website()

    # ---------- 构建托盘菜单 ----------

    def _build_menu(self):
        """
        构建右键菜单。

        pystray 的回调签名要求：
        - MenuItem.action: action(icon, item) 需要两个参数
        - MenuItem.checked: checked(item) 只有一个参数
        """

        # ---- 灵敏度菜单（db_range）----
        def checked_range(r):
            def _checked(item):
                return abs(self.get_db_range() - r) < 1e-6
            return _checked

        def action_range(r):
            def _act(icon, item):
                self._set_db_range(r)
            return _act

        # ---- 背景菜单（bg_mode）----
        def checked_bg(mode):
            def _checked(item):
                return self.get_bg_mode() == mode
            return _checked

        def action_bg(mode):
            def _act(icon, item):
                self._set_bg_mode(mode)
            return _act

        # 子菜单：灵敏度
        sens_menu = pystray.Menu(
            *[pystray.MenuItem(name, action_range(r), checked=checked_range(r))
              for (name, r) in self.db_range_choices]
        )

        # 子菜单：背景色
        bg_menu = pystray.Menu(
            *[pystray.MenuItem(name, action_bg(mode), checked=checked_bg(mode))
              for (name, mode) in self.bg_modes]
        )

        # 默认项：用于接收“主键点击”事件，再做双击判定
        # visible=False：不显示在右键菜单里
        items = []
        if getattr(pystray.Icon, "HAS_DEFAULT", True):
            items.append(pystray.MenuItem(
                "default",
                self._on_default_primary_click,
                default=True,
                visible=False
            ))
        
        # ---- 杂音滤除开关 ----
        def checked_denoise(item):
            return self.get_denoise_enabled()

        def action_toggle_denoise(icon, item):
            self._set_denoise_enabled(not self.get_denoise_enabled())

        # ---- 学习噪声画像 ----
        def action_learn_noise(icon, item):
            self._learn_noise.set()

        # ---- 强度子菜单 ----
        def checked_alpha(a):
            def _checked(item):
                return abs(self.get_denoise_alpha() - a) < 1e-9
            return _checked

        def action_alpha(a):
            def _act(icon, item):
                self._set_denoise_alpha(a)
            return _act

        denoise_strength_menu = pystray.Menu(
            *[
                pystray.MenuItem(name, action_alpha(a), checked=checked_alpha(a))
                for (name, a) in self.denoise_strength_choices
            ]
        ) 

        denoise_menu = pystray.Menu(
            pystray.MenuItem("开启过滤", action_toggle_denoise, checked=checked_denoise),
            pystray.MenuItem("学习噪声（3秒）", action_learn_noise),
            pystray.MenuItem("过滤强度", denoise_strength_menu),
            
        )

        # ---- 频段统计方式子菜单（放到“杂音滤除”里）----
        def checked_stat(mode):
            def _checked(item): return self.get_band_stat() == mode
            return _checked

        def action_stat(mode):
            def _act(icon, item): self._set_band_stat(mode)
            return _act

        stat_menu = pystray.Menu(
            *[
                pystray.MenuItem(name, action_stat(mode), checked=checked_stat(mode))
                for (name, mode) in self.band_stat_choices
            ]
        )

        # 右键菜单主项
        items += [
            pystray.MenuItem("打开官网", self._on_open_website_menu),
            pystray.MenuItem("背景色", bg_menu),
            pystray.MenuItem("灵敏度", sens_menu),
            pystray.MenuItem("频段统计", stat_menu),
            pystray.MenuItem("杂音滤除", denoise_menu),
            pystray.Menu.SEPARATOR,
            # 版本号只显示，不可点击
            pystray.MenuItem(f"版本：{__version__}", lambda icon, item: None, enabled=False),
            pystray.MenuItem("退出 (Exit)", self._on_exit),
        ]

        return pystray.Menu(*items)

    # ---------- 退出 ----------

    def _on_exit(self, icon, item):
        """退出程序：通知 worker 停止，并关闭托盘图标。"""
        self._stop.set()
        icon.stop()

    # ---------- 后台线程：采集音频并更新频谱 ----------

    def _worker(self):
        """
        后台线程主循环：

        1) 通过 soundcard 的 loopback 抓系统回放音频
        2) 每次读 nfft 帧 -> 窗函数 -> rfft -> 幅度 -> 转 dB
        3) 按频段 bins 切片，取每段的最大值 band_db（更突出瞬态/高音）
        4) 做峰值跟踪 band_peak_db：
           - 峰值每帧下降 peak_decay_db（模拟“参考峰值线”慢慢往下掉）
           - 当前 band_db 若更大则立即抬升峰值
        5) 以 (band_peak_db - db_range) 为底，以 band_peak_db 为顶，把 band_db 映射到 0..1，再映射到 0..max_level
        6) 若参数/levels 变化则重绘托盘图标
        """
        # 屏蔽 soundcard 的 discontinuity 警告（通常不影响视觉显示）
        try:
            from soundcard.mediafoundation import SoundcardRuntimeWarning
            warnings.filterwarnings("ignore", category=SoundcardRuntimeWarning)
        except Exception:
            warnings.filterwarnings("ignore", message="data discontinuity in recording")

        # # 获取默认扬声器（输出设备）
        # speaker = sc.default_speaker()
        # # 获取对应 loopback 录音源（把扬声器输出当成输入）
        # mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        mic, hint = pick_recording_source()
        if hint:
            try:
                self.icon.title = f"{APP_NAME} v{__version__}  |  {hint}"
                self.icon.update_menu()  # 部分后端不需要，但加上也无妨
            except Exception:
                pass

        sr = self.samplerate
        nfft = self.nfft

        # 预计算频段切片范围
        bins = build_band_bins(sr, nfft, n_bands=self.n_bands)

        # 汉宁窗：减少频谱泄漏（让频谱更干净）
        window = np.hanning(nfft).astype(np.float32)

        # 每个频段的峰值跟踪值（dB）
        band_peak_db = np.full(self.n_bands, -30.0, dtype=np.float32)

        # 打开录音器（双声道录制，后面会混成 mono）
        with mic.recorder(samplerate=sr, channels=2) as rec:
            # 用于“变化检测”，避免每帧都更新图标（省 CPU）
            last_levels = None
            last_db_range = None
            last_bg_mode = None
            last_stat_mode = None

            while not self._stop.is_set():
                # 阻塞读取 nfft 帧（刷新间隔约为 nfft / sr）
                data = rec.record(numframes=nfft)
                if data is None or data.size == 0:
                    continue

                # 双声道 -> 单声道（取平均）
                x = data.mean(axis=1).astype(np.float32)

                # FFT：只计算正频率部分（rfft）
                X = np.fft.rfft(x * window)

                # 幅度谱（取复数模）
                mag = np.abs(X).astype(np.float32)

                # ---------- 学习噪声画像 ----------
                if self._learn_noise.is_set():
                    self._learn_noise.clear()
                    learn_frames = max(12, int(3 * sr / nfft))
                    buf = []
                    for _ in range(learn_frames):
                        if self._stop.is_set(): break
                        data2 = rec.record(numframes=nfft)
                        if data2 is None or data2.size == 0:
                            continue
                        x2 = data2.mean(axis=1).astype(np.float32)
                        X2 = np.fft.rfft(x2 * window)
                        mag2 = np.abs(X2).astype(np.float32)
                        mag2_db = 20.0 * np.log10(mag2 + 1e-8)
                        band_db_list = []
                        for (a, b) in bins:
                            if b <= a:
                                band_db_list.append(-120.0)
                            else:
                                # 用 percentile 代替 max，抗“偶发尖峰”
                                band_db_list.append(float(np.percentile(mag2_db[a:b], 90)))
                        buf.append(band_db_list)
                    if buf:
                        noise_band = np.median(np.array(buf, dtype=np.float32), axis=0)  # 每段中位数作为噪声底
                        with self._lock:
                            self._noise_band_db = noise_band
                        self._force_redraw.set()

                # 转换到 dB：20*log10(A)
                mag_db = 20.0 * np.log10(mag + 1e-8)

                # 读取当前设置
                db_range = self.get_db_range()
                bg_mode = self.get_bg_mode()
                max_level = self.get_max_level()
                stat_mode = self.get_band_stat()

                # 计算 8 个频段的档位
                levels = []
                for i, (a, b) in enumerate(bins):
                    if b <= a:
                        # 该频段没 bin，认为极小
                        band_db = -120.0
                    else:
                        seg = mag_db[a:b]
                        ## 取最大值,更突出瞬态,尤其高频鼓点/齿音会更“跳”
                        if stat_mode == "max":
                            band_db = float(np.max(seg))
                        ## 用 90% 分位数, 更抗尖峰
                        elif stat_mode == "p90":
                            band_db = float(np.percentile(seg, 90))
                        ## 用 RMS,更接近能量
                        elif stat_mode == "rms":
                            amp = 10.0 ** (seg / 20.0)
                            band_db = float(20.0 * np.log10(np.sqrt(np.mean(amp * amp)) + 1e-12))
                        else:
                            raise ValueError(f"Unknown stat mode: {stat_mode}")

                        ## 应用滤噪, 每段做“功率域减法”再回到 dB
                        if self.get_denoise_enabled():
                            with self._lock:
                                nb = self._noise_band_db
                            if nb is not None:
                                # 功率域减法：Pclean = max(P - alpha*N, eps)
                                alpha = self.get_denoise_alpha()
                                P = 10.0 ** (band_db / 10.0)
                                N = 10.0 ** (float(nb[i]) / 10.0)
                                Pclean = max(P - alpha * N, 1e-12)
                                band_db = 10.0 * math.log10(Pclean)
                                if band_db < float(nb[i]) + self.denoise_gate_margin_db:
                                    band_db = -120.0  # 直接压到极低，柱子就不亮


                    # 峰值跟踪：峰值逐渐下降，但遇到更高值会立刻抬升
                    band_peak_db[i] = max(band_db, band_peak_db[i] - self.peak_decay_db)

                    # 归一化：
                    # - floor = 峰值 - db_range
                    # - band_db == floor -> 0
                    # - band_db == peak  -> 1
                    floor = float(band_peak_db[i] - db_range)
                    t = (band_db - floor) / db_range
                    t = clamp(t, 0.0, 1.0)

                    # 0..1 映射为 0..max_level
                    lv = int(round(t * max_level))
                    levels.append(clamp(lv, 0, max_level))

                # 菜单改动后强制重绘
                if self._force_redraw.is_set():
                    last_levels = None
                    last_db_range = None
                    last_bg_mode = None
                    last_stat_mode = None
                    self._force_redraw.clear()

                # 仅当显示内容变化时更新托盘图标
                if  (levels != last_levels) or \
                    (db_range != last_db_range) or \
                    (bg_mode != last_bg_mode) or \
                    (stat_mode != last_stat_mode):
                    self.icon.icon = make_spectrum_icon(levels, max_level, bg_mode, ICON_SIZE)
                    try:
                        self.icon.update_icon()
                    except Exception:
                        # 某些后端下更新可能抛异常，忽略即可
                        pass

                    last_levels = list(levels)
                    last_db_range = db_range
                    last_bg_mode = bg_mode
                    last_stat_mode = stat_mode

    # ---------- 启动 ----------
    def run(self):
        """启动后台线程，并进入托盘事件循环。"""
        threading.Thread(target=self._worker, daemon=True).start()
        self.icon.run()


# 程序入口
if __name__ == "__main__":
    TraySpectrumMeter(default_levels=10).run()
