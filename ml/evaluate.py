"""Model evaluation helpers — accuracy, podium precision/recall, mean position
error. Used both by the trainer (post-training metrics) and standalone CLI.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

logger = logging.getLogger(__name__)


def evaluate_model(model_path: str, validation_csv: str) -> dict:
    df = pd.read_csv(validation_csv, header=None)
    y_true, X = df.iloc[:, 0], df.iloc[:, 1:]

    model = xgb.XGBClassifier()
    model.load_model(model_path)
    y_pred = model.predict(X)

    accuracy = float(accuracy_score(y_true, y_pred))
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y_true, y_pred).tolist()

    # Mean position bracket error (treating bracket as ordinal)
    mae = float(np.mean(np.abs(y_true.to_numpy() - y_pred)))

    # Podium = classes 0 (P1) + 1 (P2-3)
    podium_true = y_true.isin([0, 1])
    podium_pred = pd.Series(y_pred).isin([0, 1]).to_numpy()
    tp = int(((podium_pred) & (podium_true.to_numpy())).sum())
    fp = int(((podium_pred) & (~podium_true.to_numpy())).sum())
    fn = int(((~podium_pred) & (podium_true.to_numpy())).sum())
    podium_precision = tp / (tp + fp) if (tp + fp) else 0
    podium_recall = tp / (tp + fn) if (tp + fn) else 0

    return {
        "accuracy": accuracy,
        "mean_bracket_error": mae,
        "podium_precision": podium_precision,
        "podium_recall": podium_recall,
        "classification_report": report,
        "confusion_matrix": matrix,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--out", default="metrics.json")
    args = parser.parse_args()
    metrics = evaluate_model(args.model, args.validation)
    Path(args.out).write_text(json.dumps(metrics, indent=2))
    logger.info("metrics written to %s", args.out)
    print(json.dumps({k: v for k, v in metrics.items() if k in ("accuracy", "podium_precision", "podium_recall", "mean_bracket_error")}, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
