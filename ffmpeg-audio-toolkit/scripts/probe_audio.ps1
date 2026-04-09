param(
  [Parameter(Mandatory = $true)]
  [string]$In,
  [string]$Ffmpeg = "ffmpeg",
  [string]$Ffprobe = "ffprobe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $In)) {
  throw "Input not found: $In"
}

# 只输出“够用”的摘要：容器、时长、音频流编码/采样率/声道等。
& $Ffprobe -hide_banner -v error -show_format -show_streams -of json -- $In

