---
name: ffmpeg-audio-toolkit
description: Use ffmpeg/ffprobe on Windows to inspect and convert audio/video files. Use for format conversion (mp3/m4a/flac/wav), resampling (e.g. 48k to 16k), channel mixing (stereo to mono), trimming, concatenation, audio extraction, loudness/volume adjustment, and generating ASR/VAD-friendly WAV (16kHz mono PCM s16le).
---

# Ffmpeg Audio Toolkit

## Overview

本 skill 用来把 ffmpeg 的常用能力固化成可直接复用的命令模板与脚本（以 Windows/PowerShell 为主），用于音频/视频的探测与转换（特别是为 VAD/ASR 准备标准 WAV）。

## Quick Start

1) 确认 ffmpeg/ffprobe 在 PATH 中可用（或使用绝对路径）

```powershell
Get-Command ffmpeg
Get-Command ffprobe
ffmpeg -version
```

2) 查看一个音频的关键信息（时长/采样率/声道/codec）

```powershell
.\scripts\probe_audio.ps1 -In .\audio.wav
```

3) 转成 VAD/ASR 友好的 WAV（16kHz、单声道、16-bit PCM）

```powershell
.\scripts\convert_to_wav16k_mono.ps1 -In .\input.any -Out .\out_16k_mono.wav
```

## Common Recipes

详细命令清单见：`references/recipes.md`（需要时再加载）。

脚本清单：
- `scripts/probe_audio.ps1`：ffprobe 摘要
- `scripts/convert_to_wav16k_mono.ps1`：转 16kHz mono PCM WAV（VAD/ASR 常用）
- `scripts/trim_audio.ps1`：裁剪片段（按秒）

说明：
- ffmpeg “格式转换”通常包含两件事：转封装（`-c copy`）或转码（指定 `-c:a/-c:v`）。
- 做 VAD/ASR 时，优先统一到 `16kHz + mono + pcm_s16le`，避免容器/编码器差异引入读取问题。
