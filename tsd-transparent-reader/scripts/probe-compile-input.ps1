param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    throw "文件不存在: $Path"
}

$headerBytes = [Text.Encoding]::ASCII.GetBytes('%TSD-Header-###%')
$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$stream = [IO.File]::Open($resolvedPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)

try {
    $isProtected = $false

    if ($stream.Length -ge $headerBytes.Length) {
        $buffer = New-Object byte[] $headerBytes.Length
        [void]$stream.Read($buffer, 0, $buffer.Length)
        $isProtected = $true

        for ($i = 0; $i -lt $headerBytes.Length; $i++) {
            if ($buffer[$i] -ne $headerBytes[$i]) {
                $isProtected = $false
                break
            }
        }
    }

    if ($isProtected) {
        Write-Output "NEEDS_PLAINTEXT`t$resolvedPath"
        exit 2
    }

    Write-Output "READY_FOR_COMPILE`t$resolvedPath"
}
finally {
    $stream.Dispose()
}
