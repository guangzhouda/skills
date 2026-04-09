---
name: 7zip-archive-toolkit
description: Use 7-Zip (7z.exe) on Windows to extract and create archives such as .zip, .7z, .tar, .gz, and multi-part volumes. Use when tasks involve extracting files, compressing folders, choosing overwrite behavior, listing archive contents, testing archive integrity, or applying archive passwords.
---

# 7zip Archive Toolkit

## Overview

Use deterministic PowerShell wrappers around 7-Zip for common archive tasks.
Prefer bundled scripts for repeatable operations and fall back to direct `7z.exe` commands for one-off actions.

## Quick Start

1) Resolve `7z.exe` path:

```powershell
$sevenZip = (Get-Command 7z -ErrorAction SilentlyContinue).Source
if (-not $sevenZip -and (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
  $sevenZip = "C:\Program Files\7-Zip\7z.exe"
}
if (-not $sevenZip) { throw "7z.exe not found" }
```

2) Extract an archive:

```powershell
.\scripts\extract-archive.ps1 -Archive "E:\input\data.zip" -OutputDir "E:\output\data" -OverwriteAll
```

3) Create an archive:

```powershell
.\scripts\compress-archive.ps1 -InputPaths "E:\data\project" -OutputArchive "E:\pkg\project.7z" -Format 7z -Level 7
```

## Common Tasks

Extract with directory structure:

```powershell
& $sevenZip x "E:\input\file.zip" "-oE:\output\dir" -y
```

Extract without directory structure (flat):

```powershell
& $sevenZip e "E:\input\file.zip" "-oE:\output\dir" -y
```

Create `.7z` archive:

```powershell
& $sevenZip a -t7z "E:\pkg\bundle.7z" "E:\src\*" -mx=7 -y
```

Create `.zip` archive:

```powershell
& $sevenZip a -tzip "E:\pkg\bundle.zip" "E:\src\*" -mx=7 -y
```

List archive contents:

```powershell
& $sevenZip l "E:\input\bundle.7z"
```

Test archive integrity:

```powershell
& $sevenZip t "E:\input\bundle.7z"
```

Create split volumes:

```powershell
& $sevenZip a -t7z "E:\pkg\big.7z" "E:\big\*" -v500m -mx=5 -y
```

## Scripts

- `scripts/extract-archive.ps1`: Extract archives with overwrite mode, flat/full extraction, and optional password.
- `scripts/compress-archive.ps1`: Create `.7z`/`.zip` archives from one or more input paths with compression level and optional password.

For option details and additional examples, read `references/7zip-commands.md`.
