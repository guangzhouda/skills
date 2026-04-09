from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


def _try_import_soundfile():
    try:
        import soundfile as sf  # type: ignore
    except Exception:
        return None
    return sf


def _try_import_torchaudio():
    try:
        import torchaudio  # type: ignore
    except Exception:
        return None
    return torchaudio


def _read_wav_via_wave(path: Path):
    # 仅兜底：标准库 wave 不支持 WAVE_FORMAT_EXTENSIBLE(65534) 等格式。
    import wave
    import numpy as np
    import torch

    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        nchan = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth == 1:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        x = (x - 128.0) / 128.0
    elif sampwidth == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = (
            a[:, 0].astype(np.int32)
            | (a[:, 1].astype(np.int32) << 8)
            | (a[:, 2].astype(np.int32) << 16)
        )
        x = (x.astype(np.int32) << 8) >> 8  # sign-extend 24-bit
        x = x.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {sampwidth} bytes")

    if nchan > 1:
        x = x.reshape(-1, nchan).mean(axis=1)

    return torch.from_numpy(x.copy()), int(sr)


def load_audio_mono(path: Path):
    """
    加载音频为单声道 float32 torch.Tensor（一维）+ 采样率。

    优先顺序：
    1) soundfile：兼容 WAVE_FORMAT_EXTENSIBLE / float wav 等
    2) 标准库 wave：兜底（仅支持部分 PCM）
    """
    import numpy as np
    import torch

    sf = _try_import_soundfile()
    if sf is not None:
        try:
            x, sr = sf.read(str(path), dtype="float32", always_2d=True)
            if x.shape[1] > 1:
                x = x.mean(axis=1, keepdims=True)
            wav = torch.from_numpy(np.ascontiguousarray(x[:, 0]))
            return wav, int(sr)
        except Exception:
            pass

    return _read_wav_via_wave(path)


def resample_if_needed(wav, sr: int, target_sr: int):
    if sr == target_sr:
        return wav, sr

    torchaudio = _try_import_torchaudio()
    if torchaudio is None:
        raise RuntimeError(
            "torchaudio is required for resampling in this script. "
            "Run this with the silero-vad repo venv (usually has torchaudio)."
        )

    wav2 = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr)(
        wav.unsqueeze(0)
    ).squeeze(0)
    return wav2, target_sr


def segments_complement(duration_s: float, speech: list[tuple[float, float]]):
    non_speech: list[tuple[float, float]] = []
    cur = 0.0
    for s, e in speech:
        if s > cur:
            non_speech.append((cur, s))
        cur = max(cur, e)
    if cur < duration_s:
        non_speech.append((cur, duration_s))
    return non_speech


def _round_segments(segs: Iterable[tuple[float, float]], ndigits: int | None):
    if ndigits is None:
        return [(float(s), float(e)) for s, e in segs]
    return [(round(float(s), ndigits), round(float(e), ndigits)) for s, e in segs]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Run Silero VAD (local repo) and output speech/non-speech segments as JSON."
    )
    p.add_argument("--repo", required=True, help="Path to local silero-vad repo (contains src/).")
    p.add_argument("--wav", required=True, help="Path to audio file (WAV recommended).")
    p.add_argument("--target-sr", type=int, default=16000, help="Resample audio to this SR (default: 16000).")

    # Expose common get_speech_timestamps knobs.
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--neg-threshold", type=float, default=None)
    p.add_argument("--min-speech-ms", type=int, default=250)
    p.add_argument("--max-speech-s", type=float, default=float("inf"))
    p.add_argument("--min-silence-ms", type=int, default=100)
    p.add_argument("--speech-pad-ms", type=int, default=30)

    p.add_argument("--onnx", action="store_true", help="Use ONNX model instead of JIT.")
    p.add_argument("--opset", type=int, default=16, help="ONNX opset_version (15/16).")
    p.add_argument("--round", dest="round_ndigits", type=int, default=3, help="Round seconds to N digits (default: 3). Use -1 to disable.")
    args = p.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    wav_path = Path(args.wav).expanduser().resolve()
    if not repo.exists():
        raise SystemExit(f"--repo not found: {repo}")
    if not (repo / "src").exists():
        raise SystemExit(f"--repo does not look like silero-vad repo (missing src/): {repo}")
    if not wav_path.exists():
        raise SystemExit(f"--wav not found: {wav_path}")

    # Make local repo importable without installing.
    sys.path.insert(0, str(repo / "src"))

    import torch  # noqa: E402

    from silero_vad.model import load_silero_vad  # noqa: E402
    from silero_vad.utils_vad import get_speech_timestamps  # noqa: E402

    wav, sr = load_audio_mono(wav_path)
    wav, sr = resample_if_needed(wav, sr, int(args.target_sr))
    duration_s = float(wav.numel()) / float(sr)

    model = load_silero_vad(onnx=bool(args.onnx), opset_version=int(args.opset))

    speech_dicts = get_speech_timestamps(
        wav,
        model,
        threshold=float(args.threshold),
        sampling_rate=int(sr),
        min_speech_duration_ms=int(args.min_speech_ms),
        max_speech_duration_s=float(args.max_speech_s),
        min_silence_duration_ms=int(args.min_silence_ms),
        speech_pad_ms=int(args.speech_pad_ms),
        return_seconds=True,
        neg_threshold=(None if args.neg_threshold is None else float(args.neg_threshold)),
    )

    speech_segments = [(float(d["start"]), float(d["end"])) for d in speech_dicts]
    non_speech_segments = segments_complement(duration_s, speech_segments)

    nd = None if int(args.round_ndigits) < 0 else int(args.round_ndigits)
    out = {
        "file": str(wav_path),
        "repo": str(repo),
        "sampling_rate": int(sr),
        "duration_s": round(duration_s, 6) if nd is not None else duration_s,
        "speech": _round_segments(speech_segments, nd),
        "non_speech": _round_segments(non_speech_segments, nd),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # Avoid unused import warning in some linters; keep torch visible for runtime env debugging.
    _ = torch.__version__
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

