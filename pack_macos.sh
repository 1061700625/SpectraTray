#!/usr/bin/env bash
set -euo pipefail

echo "0、准备干净的环境。"

python -m venv tray
# shellcheck disable=SC1091
source tray/bin/activate
pip install -i https://pypi.org/simple pystray pillow numpy SoundCard pyobjc

echo "1、创建原生启动器 App。"

mkdir -p SpectraTray.app/Contents/{MacOS,Resources}
mkdir -p SpectraTray.app/Contents/Resources/pysrc
cp app.py SpectraTray.app/Contents/Resources/pysrc/
cp -R tray SpectraTray.app/Contents/Resources/tray
cp SpectraTray.ico SpectraTray.app/Contents/Resources/

echo "2、写 Swift 启动器。"

cat > main.swift <<'SWIFT'
import Foundation
import AVFoundation

func runPython() {
    let bundleURL = Bundle.main.bundleURL
    let py = bundleURL.appendingPathComponent("Contents/Resources/tray/bin/python3").path
    let script = bundleURL.appendingPathComponent("Contents/Resources/pysrc/app.py").path

    let task = Process()
    task.executableURL = URL(fileURLWithPath: py)
    task.arguments = [script]

    // 完全后台（不弹终端）
    task.standardOutput = FileHandle.nullDevice
    task.standardError  = FileHandle.nullDevice

    do { try task.run() } catch { }

    exit(0)
}

// 先触发一次麦克风权限（允许后 python 才能录到 BlackHole）
AVCaptureDevice.requestAccess(for: .audio) { _ in
    runPython()
}

RunLoop.main.run()
SWIFT

swiftc main.swift -o SpectraTray.app/Contents/MacOS/SpectraTray

echo "3、写 Info.plist。"

cat > SpectraTray.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>SpectraTray</string>
  <key>CFBundleDisplayName</key><string>SpectraTray</string>
  <key>CFBundleIdentifier</key><string>local.spectratray</string>
  <key>CFBundleExecutable</key><string>SpectraTray</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.0.2</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleIconFile</key><string>SpectraTray.ico</string>
  <key>LSBackgroundOnly</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>用于捕获系统音频（如 BlackHole）并显示实时频谱</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict>
</plist>
PLIST

echo "4、去掉 quarantine。"

xattr -dr com.apple.quarantine SpectraTray.app

echo "5、刷新图标。"

touch SpectraTray.app

echo "✅ 完成：SpectraTray.app"
