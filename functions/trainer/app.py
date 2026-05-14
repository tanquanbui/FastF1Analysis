"""Trainer Lambda — assembles training dataset and launches SageMaker job.

Triggered monthly by EventBridge. Steps:

  1. Pull (driver, race) features from DynamoDB for the chosen years.
  2. Split 80/20 into train.csv / validation.csv.
  3. Upload to ``s3://pitstop-models/training/<timestamp>/``.
  4. Launch a SageMaker training job with the built-in XGBoost container.
  5. Tag the resulting ``model.tar.gz`` so the predictor knows which version
     to load.
"""
from __future__ import annotations

import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

# `features` and `circuit_profiler` come from the shared Lambda Layer mounted
# at /opt/python/. Locally during tests the pytest pythonpath adds shared/python/.
sys.path.insert(0, str(Path(__file__).parent))

from feature_builder import FeatureBuilder  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sagemaker = boto3.client("sagemaker")

TABLE_NAME = os.environ["TABLE_NAME"]
MODELS_BUCKET = os.environ["MODELS_BUCKET"]
SAGEMAKER_ROLE = os.environ.get("SAGEMAKER_ROLE_ARN", "")
REGION = os.environ.get("AWS_REGION", "ap-southeast-2")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point."""
    years = event.get("years") or list(range(2020, datetime.now(timezone.utc).year + 1))
    val_split = float(event.get("validation_split", 0.2))
    seed = int(event.get("seed", 42))
    skip_training = bool(event.get("skip_training", False))

    logger.info("building training set for years=%s", years)
    builder = FeatureBuilder(dynamodb.Table(TABLE_NAME))
    rows, labels = builder.build_training_set(years)
    if not rows:
        return {"statusCode": 200, "body": {"error": "no training data found"}}
    logger.info("assembled %d rows", len(rows))

    train_rows, train_labels, valid_rows, valid_labels = _split(rows, labels, val_split, seed)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = f"training/{timestamp}"

    train_csv = builder.to_csv(train_rows, train_labels)
    valid_csv = builder.to_csv(valid_rows, valid_labels)

    train_key = f"{prefix}/train.csv"
    valid_key = f"{prefix}/validation.csv"
    _upload(MODELS_BUCKET, train_key, train_csv)
    _upload(MODELS_BUCKET, valid_key, valid_csv)
    logger.info("uploaded train.csv (%d rows) + validation.csv (%d rows) to s3://%s/%s",
                len(train_rows), len(valid_rows), MODELS_BUCKET, prefix)

    if skip_training:
        return {"statusCode": 200, "body": {"prefix": prefix, "training_skipped": True}}

    job_name = _launch_training_job(prefix, train_key, valid_key, timestamp)
    return {
        "statusCode": 200,
        "body": {
            "prefix": prefix,
            "job_name": job_name,
            "train_rows": len(train_rows),
            "validation_rows": len(valid_rows),
        },
    }


def _split(rows, labels, val_split, seed):
    random.seed(seed)
    indices = list(range(len(rows)))
    random.shuffle(indices)
    cutoff = int(len(indices) * (1 - val_split))
    train_idx = indices[:cutoff]
    valid_idx = indices[cutoff:]
    return (
        [rows[i] for i in train_idx],
        [labels[i] for i in train_idx],
        [rows[i] for i in valid_idx],
        [labels[i] for i in valid_idx],
    )


def _upload(bucket: str, key: str, body: str) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="text/csv")


def _launch_training_job(prefix: str, train_key: str, valid_key: str, timestamp: str) -> str:
    """Launch SageMaker's built-in XGBoost container."""
    if not SAGEMAKER_ROLE:
        raise RuntimeError("SAGEMAKER_ROLE_ARN env var not configured")

    job_name = f"pitstop-xgboost-{timestamp}"
    container_image = _xgboost_container_image()
    sagemaker.create_training_job(
        TrainingJobName=job_name,
        AlgorithmSpecification={
            "TrainingImage": container_image,
            "TrainingInputMode": "File",
        },
        RoleArn=SAGEMAKER_ROLE,
        InputDataConfig=[
            {
                "ChannelName": "train",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": f"s3://{MODELS_BUCKET}/{train_key}",
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "text/csv",
            },
            {
                "ChannelName": "validation",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": f"s3://{MODELS_BUCKET}/{valid_key}",
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "text/csv",
            },
        ],
        OutputDataConfig={"S3OutputPath": f"s3://{MODELS_BUCKET}/{prefix}/model/"},
        ResourceConfig={
            "InstanceType": "ml.m5.large",
            "InstanceCount": 1,
            "VolumeSizeInGB": 5,
        },
        StoppingCondition={"MaxRuntimeInSeconds": 1800},
        HyperParameters={
            "objective": "multi:softprob",
            "num_class": "5",
            "num_round": "200",
            "max_depth": "6",
            "eta": "0.1",
            "subsample": "0.8",
            "verbosity": "1",
        },
    )
    logger.info("launched training job %s", job_name)
    return job_name


def _xgboost_container_image() -> str:
    """SageMaker XGBoost built-in container URI for the deployed region."""
    region_account = {
        "us-east-1": "683313688378",
        "us-west-2": "246618743249",
        "eu-west-1": "685385470294",
        "ap-southeast-2": "783357654285",
        "ap-southeast-1": "121021644041",
    }
    account = region_account.get(REGION, "783357654285")
    return f"{account}.dkr.ecr.{REGION}.amazonaws.com/sagemaker-xgboost:1.7-1"
