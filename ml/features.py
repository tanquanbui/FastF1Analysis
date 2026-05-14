"""Re-export from the shared Layer so SageMaker scripts and Lambda code see
the same feature definitions.

The canonical implementation is ``shared/python/features.py``. We load it via
``importlib`` to avoid the obvious self-import collision (since this file is
also named ``features.py``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_canonical = Path(__file__).resolve().parent.parent / "shared" / "python" / "features.py"
if not _canonical.exists():
    raise ImportError(f"Shared features.py not found at {_canonical}")

_spec = importlib.util.spec_from_file_location("_pitstop_shared_features", _canonical)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)

POSITION_BUCKETS = _module.POSITION_BUCKETS
TARGET_COLUMN = _module.TARGET_COLUMN
TRAINING_FEATURES = _module.TRAINING_FEATURES
build_feature_row = _module.build_feature_row
position_to_bucket = _module.position_to_bucket
row_to_csv = _module.row_to_csv
