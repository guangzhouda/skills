param(
  [Parameter(Mandatory = $true)]
  [string]$In,
  [Parameter(Mandatory = $true)]
  [string]$Out,
  [string]$Ffmpeg = "ffmpeg"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $In)) {
  throw "Input not found: $In"
}

$outDir = Split-Path -Parent $Out
if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

# 统一转成：16kHz + mono + 16-bit PCM WAV
& $Ffmpeg -y -hide_banner -i $In -ac 1 -ar 16000 -c:a pcm_s16le $Out

