---
name: tsd-transparent-reader
description: "Read and migrate Windows transparent-encryption text files that show a `%TSD-Header-###%` header or behave like TSafe Doc/EnUES protected files. Use when direct file reads return ciphertext or gibberish, Notepad can open the file normally, and Codex needs to: (1) extract plaintext for editing, (2) validate whether encrypted script files can run directly, or (3) replace encrypted source files with plaintext working copies before compilation while backing up the originals."
---

# Tsd Transparent Reader

Use this skill when a file is transparently decrypted for trusted GUI programs such as `notepad.exe`, but direct reads from PowerShell, `type`, normal libraries, or compiler frontends return ciphertext.

## Capabilities
1. Read one protected file to get plaintext before editing.
2. Restore one or many protected files to plaintext working copies while moving the original encrypted files into a sibling backup directory named `加密`.
3. Decide whether a task can use the encrypted file directly:
   - For script runtime validation, try direct execution first.
   - For source inspection or editing, use the reader script directly; do not ask users to rename suffixes by hand.

## Quick Start
Read one protected file:

```powershell
powershell -STA -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\tsd-transparent-reader\scripts\read-tsd-hidden.ps1" "E:\tmp\待处理.c"
```

Read one protected file and write the plaintext directly to a file without going through stdout:

```powershell
powershell -STA -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\tsd-transparent-reader\scripts\read-tsd-hidden.ps1" "E:\tmp\待处理.c" -OutputPath "E:\tmp\待处理.plain.c"
```

Check whether a file must be restored before compilation:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\tsd-transparent-reader\scripts\probe-compile-input.ps1" "E:\tmp\example.c"
```

Migrate protected files to plaintext in place and back up originals to `加密`:

```powershell
powershell -STA -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\tsd-transparent-reader\scripts\restore-tsd-text.ps1" -Paths "E:\tmp\123.c","E:\tmp\1234.c","E:\tmp\待处理.c"
```

## Decision Rules
- If the user needs to modify a protected file, read plaintext first with `scripts/read-tsd-hidden.ps1`.
- If the user needs to run an interpreted script such as `.py`, `.ps1`, or similar, prefer the real runtime process first. Only restore to plaintext if direct execution fails or if the file must be edited.
- If the user only needs to read plaintext, check the `%TSD-Header-###%` header first and then use `scripts/read-tsd-hidden.ps1`. Do not use compiler probing for this case.
- No manual extension rename is required. `scripts/read-tsd-hidden.ps1` will retry through a temporary `.c` copy automatically when the original extension still shows `%TSD-Header-###%` ciphertext in Notepad.
- `scripts/probe-compile-input.ps1` is only a header check. Use it to decide whether the file is still protected, not to trigger heavier validation.

## Detection Rules
- Treat files beginning with the ASCII header `%TSD-Header-###%` as protected TSD files.
- Treat files that render as ciphertext in direct reads but open correctly in Notepad as candidates even if the header check is not available yet.
- Do not use Notepad++ as the decoder path; on this machine it loads the protection DLL but still shows ciphertext.

## Notes
- The scripts still launch `notepad.exe`, but they keep it minimized and close it immediately after reading the editor control.
- `read-tsd-hidden.ps1` now retries protected files through a temporary `.c` copy when the original extension still shows `%TSD-Header-###%` ciphertext in Notepad, which fixes observed `.py` cases on this machine.
- If you need to persist multi-line plaintext, prefer `-OutputPath` or `restore-tsd-text.ps1`; do not capture child PowerShell stdout and then write it back, or line breaks may collapse.
- The restore script writes plaintext with UTF-8 without BOM and does not append a trailing newline.
- The restore script skips files that do not match the TSD header unless `-Force` is provided.
- Current observed behavior on this machine:
  - Encrypted `.py` files can still be executed by `python.exe`.
  - Manual suffix changes are unnecessary for the reader script; it handles the temporary `.c` retry internally.
  - For plain content extraction, header check + reader script is the preferred path on this machine.
