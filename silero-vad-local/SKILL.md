---
name: silero-vad-local
description: Run Silero VAD from a local silero-vad repo checkout (Windows-friendly) to segment audio into speech and non-speech intervals. Use when you need VAD timestamps for WAV (including WAVE_FORMAT_EXTENSIBLE), want to tune VAD thresholds/durations, or need streaming VAD via VADIterator/ONNX.
---

# Silero Vad Local

## Overview

在本机使用 `silero-vad`（本地仓库 + 本地模型文件）对音频做 VAD，输出 `speech` / `non_speech` 时间段，并支持常用参数调优与流式用法指引。

## Quick Start（离线/本地仓库）

1) 选择 Python 环境（推荐用仓库自带 venv）

优先使用：
- `<silero_repo>\\.venv\\Scripts\\python.exe`（通常已有 `torch/torchaudio/silero_vad` 依赖）

2) 运行分段脚本（输出 JSON）

```powershell
& E:\Projects\silero-vad\.venv\Scripts\python.exe `
  C:\Users\jing.ao\.codex\skills\silero-vad-local\scripts\run_vad_segments.py `
  --repo E:\Projects\silero-vad `
  --wav  D:\path\to\audio.wav
```

说明：
- 默认将音频重采样到 16k（Silero VAD 最常用配置）。
- Windows 上遇到 `WAVE_FORMAT_EXTENSIBLE (65534)` 时，脚本会优先用 `soundfile` 读入（比 `wave` 更兼容）。

## Tune Parameters（常用调参）

```powershell
& E:\Projects\silero-vad\.venv\Scripts\python.exe `
  C:\Users\jing.ao\.codex\skills\silero-vad-local\scripts\run_vad_segments.py `
  --repo E:\Projects\silero-vad `
  --wav  D:\path\to\audio.wav `
  --threshold 0.6 `
  --min-speech-ms 200 `
  --min-silence-ms 120 `
  --speech-pad-ms 30
```

关键参数映射到 `silero_vad.utils_vad.get_speech_timestamps()`：
- `--threshold`：判为 speech 的概率阈值
- `--neg-threshold`：退出 speech 的阈值（默认 `threshold - 0.15`）
- `--min-speech-ms`：最短语音段（小于则丢弃）
- `--min-silence-ms`：语音段之间的最短静音分割
- `--speech-pad-ms`：语音段左右 padding（避免切太紧）
- `--max-speech-s`：单段最长语音（超长会在静音处切分）

## Streaming / ONNX / More Capabilities

需要更多能力时，读取 `references/capabilities.md`：
- `VADIterator`（流式逐块推理）
- `collect_chunks()` / `drop_chunks()`（按时间戳裁剪/丢弃片段）
- ONNX/JIT 选择、`light_vad_runtime`（无 torch 的 onnx-lite 运行时）

脚本入口：
- `scripts/run_vad_segments.py`
