"""Load the latest XGBoost model artifact from S3 and cache it across warm
Lambda invocations.
"""
from __future__ import annotations

import logging
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import boto3
import xgboost as xgb

logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
_model_cache: dict[str, Any] = {}


def load_latest_model(bucket: str, prefix: str = "training/") -> xgb.XGBClassifier:
    """Look up the most recent training/<timestamp>/model/ artefact and load it.

    The SageMaker XGBoost container packs the trained model into ``model.tar.gz``
    inside the output directory. We extract and load with the Python API.
    """
    cache_key = bucket
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    candidates = sorted(
        (c["Prefix"].rstrip("/") for c in (response.get("CommonPrefixes") or [])),
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"no training prefixes under s3://{bucket}/{prefix}")

    for candidate in candidates:
        artefact_key = f"{candidate}/model/output/model.tar.gz"
        try:
            return _load_artefact(bucket, artefact_key)
        except s3.exceptions.NoSuchKey:
            logger.warning("missing %s; trying older training run", artefact_key)
            continue
    raise RuntimeError("no valid model artefact found")


def _load_artefact(bucket: str, key: str) -> xgb.XGBClassifier:
    """Download a model.tar.gz, untar, and load."""
    with tempfile.TemporaryDirectory() as tmp:
        local_tar = Path(tmp) / "model.tar.gz"
        s3.download_file(bucket, key, str(local_tar))
        with tarfile.open(local_tar, "r:gz") as t:
            t.extractall(tmp)

        json_path = next(Path(tmp).rglob("*.json"), None)
        bst_path = next(Path(tmp).rglob("xgboost-model"), None)

        model = xgb.XGBClassifier()
        if json_path:
            model.load_model(str(json_path))
        elif bst_path:
            model.load_model(str(bst_path))
        else:
            raise RuntimeError(f"no recognisable model file inside {key}")

        _model_cache[bucket] = model
        logger.info("loaded model from s3://%s/%s", bucket, key)
        return model
