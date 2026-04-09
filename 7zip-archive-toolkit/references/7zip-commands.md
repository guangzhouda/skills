# 7-Zip Command Notes (Windows)

## Core Verbs

- `a`: Add files to archive (create/update)
- `x`: Extract with full paths
- `e`: Extract without paths (flat)
- `l`: List archive contents
- `t`: Test archive integrity

## Common Options

- `-t7z` / `-tzip`: Archive type
- `-mx=0..9`: Compression level
- `-y`: Assume yes on all prompts
- `-aos`: Skip extracting files that already exist
- `-aoa`: Overwrite all existing files
- `-v<size>`: Split archive volumes (e.g., `-v500m`)
- `-pPASSWORD`: Password
- `-mhe=on`: Encrypt file names (7z format)

## Examples

Extract to specific folder:

```powershell
& "C:\Program Files\7-Zip\7z.exe" x "E:\in\data.7z" "-oE:\out\data" -y
```

Create zip from folder:

```powershell
& "C:\Program Files\7-Zip\7z.exe" a -tzip "E:\pkg\data.zip" "E:\data\*" -mx=7 -y
```

Test an archive:

```powershell
& "C:\Program Files\7-Zip\7z.exe" t "E:\pkg\data.7z"
```
