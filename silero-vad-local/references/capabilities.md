# silero-vad 能力速查（本地仓库）

本文件用于在需要“更多能力/更多用法”时被 Codex 按需加载；不需要时不要加载。

## 核心 API（Python）

代码位置（本地仓库）：
- `E:\Projects\silero-vad\src\silero_vad\model.py`：`load_silero_vad(onnx=False, opset_version=16)`
- `E:\Projects\silero-vad\src\silero_vad\utils_vad.py`：
  - `get_speech_timestamps(...)`：离线/整段音频切分（返回 start/end）
  - `VADIterator`：流式（逐块）推理
  - `collect_chunks(tss, wav)`：按时间戳把 speech 片段拼起来
  - `drop_chunks(tss, wav)`：按时间戳把 speech 片段从音频中移除

### get_speech_timestamps 常用参数（调参入口）

可调参数（最常用）：
- `threshold`：speech 概率阈值（默认 0.5）
- `neg_threshold`：退出 speech 的阈值（默认 `threshold - 0.15`）
- `min_speech_duration_ms`：最短语音段（短于则丢弃）
- `min_silence_duration_ms`：静音分割条件（越大越“保守”切分）
- `speech_pad_ms`：语音段左右 padding
- `max_speech_duration_s`：单段最长语音（超长会尝试在静音处切）
- `return_seconds`：返回秒（否则返回 sample index）
- `time_resolution`：秒级时间分辨率（通常保持默认）

### VADIterator（流式）

用途：
- 麦克风/WebRTC/实时音频：按固定 chunk 输入，持续拿到 speech 概率与段落边界。

参考实现：
- `E:\Projects\silero-vad\examples\pyaudio-streaming\README.md`
- `E:\Projects\silero-vad\examples\microphone_and_webRTC_integration\`

## 模型/运行时选择

JIT（默认）：
- 优点：简单，依赖少；通常够用
- `load_silero_vad(onnx=False)`

ONNX：
- 优点：跨平台推理/与 onnxruntime 集成更方便
- `load_silero_vad(onnx=True, opset_version=16)`（也支持 15）

ONNX Lite（无 torch 的轻量封装）：
- 位置：`E:\Projects\silero-vad\light_vad_runtime\`
- 适用：想完全绕开 torch/torchaudio，仅依赖 `onnxruntime+numpy` 等

## Windows 音频 I/O 兼容性提示

- `WAVE_FORMAT_EXTENSIBLE (65534)` 的 wav，标准库 `wave` 可能报错。
- 解决：优先用 `soundfile`（libsndfile）读取；本 skill 的脚本 `scripts/run_vad_segments.py` 已优先使用 `soundfile`。

