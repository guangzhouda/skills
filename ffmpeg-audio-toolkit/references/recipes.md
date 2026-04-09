# ffmpeg 常用能力速查（Windows / PowerShell）

本文件用于在需要“更多 ffmpeg 用法”时按需加载；不需要时不要加载。

## 0) 先探测：ffprobe/ffmpeg 能看到什么

### 查看容器/编码/采样率/声道/时长（推荐）
```powershell
ffprobe -hide_banner -v error -show_format -show_streams -of json .\input.any
```

### 仅显示音频流关键信息（更短）
```powershell
ffprobe -hide_banner -v error -select_streams a:0 `
  -show_entries stream=codec_name,codec_type,sample_rate,channels,channel_layout,bit_rate,duration `
  -of default=nw=1:nk=1 .\input.any
```

## 1) 格式转换（转封装 vs 转码）

### 1.1 转封装（不重编码，速度快）
适用：源音频编码能被目标容器接受。

```powershell
ffmpeg -y -i .\in.m4a -c copy .\out.mp4
```

### 1.2 转码（指定编码器）

#### MP3 -> WAV（16kHz/mono/PCM16，VAD/ASR 友好）
```powershell
ffmpeg -y -i .\in.mp3 -ac 1 -ar 16000 -c:a pcm_s16le .\out.wav
```

#### 任意输入 -> FLAC（无损压缩）
```powershell
ffmpeg -y -i .\in.any -c:a flac .\out.flac
```

#### 任意输入 -> AAC（m4a）
```powershell
ffmpeg -y -i .\in.any -c:a aac -b:a 128k .\out.m4a
```

## 2) 采样率/声道转换（重采样/混音）

### 2.1 重采样到 16kHz + 单声道（最常用）
```powershell
ffmpeg -y -i .\in.any -ac 1 -ar 16000 -c:a pcm_s16le .\out_16k_mono.wav
```

### 2.2 仅改声道，不改采样率/编码（尽量避免，取决于容器/编码器）
```powershell
ffmpeg -y -i .\in.any -ac 1 .\out.any
```

## 3) 裁剪/截取（trim）

### 3.1 截取片段（推荐写法：先 -ss 再 -t）
```powershell
ffmpeg -y -ss 12.3 -t 5.0 -i .\in.any -c:a pcm_s16le .\clip.wav
```

### 3.2 到某个结束时间（-to）
```powershell
ffmpeg -y -ss 12.3 -to 17.3 -i .\in.any -c:a pcm_s16le .\clip.wav
```

## 4) 拼接（concat）

### 4.1 同编码/同参数文件（无损拼接）
1) 写 `list.txt`：
```text
file 'a.wav'
file 'b.wav'
```
2) concat：
```powershell
ffmpeg -y -f concat -safe 0 -i .\list.txt -c copy .\out.wav
```

若失败：通常是采样率/声道/编码不一致，先统一转成同格式再 concat。

## 5) 抽取音频（从视频）
```powershell
ffmpeg -y -i .\in.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le .\audio.wav
```

## 6) 调音量/响度（常用两种）

### 6.1 线性/分贝调音量
```powershell
ffmpeg -y -i .\in.wav -af \"volume=-6dB\" .\out.wav
```

### 6.2 EBU R128 响度归一（更“工程化”）
两遍法（更稳）：
```powershell
ffmpeg -y -i .\in.wav -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null NUL
```
再把测得的参数填回第二遍（此处略；不同文件参数不同）。

## 7) 生成可视化（排查问题）

### 7.1 画波形图（png）
```powershell
ffmpeg -y -i .\in.wav -filter_complex \"showwavespic=s=1200x200\" -frames:v 1 .\wave.png
```

### 7.2 画频谱（png）
```powershell
ffmpeg -y -i .\in.wav -lavfi showspectrumpic=s=1200x400:legend=1 -frames:v 1 .\spec.png
```

## 8) 常见坑（你已经遇到过的）

- “文件扩展名是 .wav”不代表一定是 RIFF WAV；例如文件头是 `ID3` 时，`scipy.io.wavfile` 会读失败，但 ffmpeg/soundfile 往往能读。
- 为 VAD/ASR 做预处理时，建议统一输出：`16kHz + mono + pcm_s16le`，能显著减少 I/O 与兼容性问题。

