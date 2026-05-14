"""SageMaker XGBoost entrypoint for local-mode training.

In production the trainer Lambda launches a SageMaker training job using the
built-in XGBoost container, which uses ``train.csv`` and ``validation.csv``
files written to S3 by ``feature_builder.py``. This script is useful for:

  * local sanity-checks before pushing to SageMaker
  * the SageMaker "script mode" alternative if we ever need custom logic
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, accuracy_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def train(args: argparse.Namespace) -> None:
    train_df = pd.read_csv(args.train, header=None)
    valid_df = pd.read_csv(args.validation, header=None)

    y_train, X_train = train_df.iloc[:, 0], train_df.iloc[:, 1:]
    y_valid, X_valid = valid_df.iloc[:, 0], valid_df.iloc[:, 1:]

    logger.info("training on %d rows, %d features", len(X_train), X_train.shape[1])

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=5,  # P1, P2-3, P4-5, P6-10, P11+
        n_estimators=args.num_round,
        max_depth=args.max_depth,
        learning_rate=args.eta,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        tree_method="hist",
        eval_metric="mlogloss",
        random_state=42,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_valid, y_valid)],
        verbose=False,
    )

    preds = model.predict(X_valid)
    accuracy = accuracy_score(y_valid, preds)
    report = classification_report(y_valid, preds, output_dict=True, zero_division=0)
    logger.info("validation accuracy: %.4f", accuracy)
    logger.info(
        "podium precision/recall (classes 0+1): P=%.3f / R=%.3f",
        (report["0"]["precision"] + report["1"]["precision"]) / 2,
        (report["0"]["recall"] + report["1"]["recall"]) / 2,
    )

    output_dir = Path(args.model_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_dir / "model.json"))

    metrics = {
        "accuracy": accuracy,
        "validation_classification_report": report,
        "feature_importance": dict(zip(
            [f"f{i}" for i in range(X_train.shape[1])],
            model.feature_importances_.tolist(),
        )),
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info("model + metrics written to %s", output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data/train.csv"))
    parser.add_argument("--validation", default=os.environ.get("SM_CHANNEL_VALIDATION", "data/validation.csv"))
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model/"))
    parser.add_argument("--num-round", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--eta", type=float, default=0.1)
    parser.add_argument("--subsample", type=float, default=0.8)
    parser.add_argument("--colsample-bytree", type=float, default=0.8)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
