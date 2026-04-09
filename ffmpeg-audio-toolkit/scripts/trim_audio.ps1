param(
  [Parameter(Mandatory = $true)]
  [string]$In,
  [Parameter(Mandatory = $true)]
  [string]$Out,
  [Parameter(Mandatory = $true)]
  [double]$StartSeconds,
  [Parameter(Mandatory = $true)]
  [double]$DurationSeconds,
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

# 先 -ss 再 -t：通常更快（尤其是长文件）。
& $Ffmpeg -y -hide_banner -ss $StartSeconds -t $DurationSeconds -i $In -c:a pcm_s16le $Out

