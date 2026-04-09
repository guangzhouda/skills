---
name: hf-download-record
description: Download Hugging Face models or datasets with huggingface-cli, record local snapshot/cache paths, and update code to use local snapshots for offline inference. Use when the user wants manual HF downloads, needs the exact local snapshot path, or wants to avoid network downloads during inference.
---

# HF Download Record

## Overview

Download HF artifacts locally, capture the snapshot path, and wire code to load from disk without network access.

## Workflow

1. Check or set cache location (HF_HOME).
2. Download with huggingface-cli.
3. Find the snapshot directory and verify required files exist.
4. Update code to point to the local snapshot.
5. Enable offline mode for inference.
6. Run a quick verification command and record outputs.

## Commands (PowerShell)

Download:
```
huggingface-cli download <repo-id>
```

Locate snapshot (model example):
```
Get-ChildItem "$env:HF_HOME\\hub\\models--<org>--<repo>\\snapshots"
```

Offline mode for inference:
```
$env:HF_HUB_OFFLINE="1"
```

## Code Wiring (SpeechBrain example)

Use the snapshot directory as the source:
```
from speechbrain.inference.separation import SepformerSeparation as Separator
from speechbrain.utils.fetching import LocalStrategy

model = Separator.from_hparams(
    source=r"<snapshot-dir>",
    pymodule_file="hyperparams.yaml",
    savedir="pretrained_models/sepformer-wsj02mix",
    local_strategy=LocalStrategy.COPY,
)
```

## Notes

- If the snapshot directory lacks `custom.py`, set `pymodule_file` to a file that exists (e.g., `hyperparams.yaml`).
- On Windows, prefer `LocalStrategy.COPY` to avoid symlink issues.
