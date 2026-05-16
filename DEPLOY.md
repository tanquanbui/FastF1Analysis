# Deploy runbook — PitStop Analytics

This file walks you from a fresh clone to a live `dev` stack in `ap-southeast-2`. Every step says **why** so you can stop and ask if something looks off.

> **Total time:** ~25 min on a typical broadband connection (most of it is `sam build` pulling Python wheels and the first CloudFront propagation).

---

## 0. Prerequisites — install once

| Tool | Version | Install |
|---|---|---|
| AWS CLI | v2 | `brew install awscli` |
| SAM CLI | ≥ 1.100 | `brew install aws-sam-cli` |
| Python | 3.11 | `brew install python@3.11` |
| jq | any | `brew install jq` |
| Docker | optional | `brew install --cask docker` (only needed if you pass `sam build --use-container`) |

Verify:

```bash
aws --version          # → aws-cli/2.x.x
sam --version          # → SAM CLI, version 1.1xx
python3 --version      # → Python 3.11.x
```

---

## 1. Configure AWS credentials

Pick **one** of these — don't mix them.

### Option A (recommended): SSO

```bash
aws configure sso
# SSO start URL: https://<your-org>.awsapps.com/start
# Region: ap-southeast-2
# Profile name: pitstop-dev
export AWS_PROFILE=pitstop-dev
export AWS_REGION=ap-southeast-2
```

### Option B: Access keys (only if SSO isn't available)

```bash
aws configure --profile pitstop-dev
# AWS Access Key ID:     AKIA...
# AWS Secret Access Key: ...
# Default region name:   ap-southeast-2
export AWS_PROFILE=pitstop-dev
```

**Sanity check** — this must succeed before you go further:

```bash
aws sts get-caller-identity
# {
#   "UserId": "AIDA...",
#   "Account": "123456789012",
#   "Arn":     "arn:aws:iam::123456789012:user/you"
# }
```

If you see `InvalidClientTokenId` or `ExpiredToken`, re-run `aws sso login --profile pitstop-dev`.

---

## 2. Install dependencies

```bash
cd /Users/quantanbui/Documents/FastF1Analysis
python3 -m venv .venv
source .venv/bin/activate
make install
```

> **Why a venv:** keeps `fastf1`, `xgboost` and friends isolated from your system Python. Subsequent commands assume the venv is active — re-run `source .venv/bin/activate` in new terminals.

---

## 3. Preflight — local sanity checks

```bash
make preflight
```

This runs in order:

1. `compile-check` — every `.py` file is syntactically valid.
2. `test-all` — 85+ unit tests across 6 Lambda functions, all with mocked AWS.
3. `validate` — `sam validate --lint` on `template.yaml` against AWS's CloudFormation schema.

**Stop here if any step fails.** Don't paper over a failing test with `--no-fail-on-empty-changeset` later — preflight failures predict deploy failures.

---

## 4. First-time `sam deploy --guided`

```bash
make build           # ~2-3 min (packages every Lambda)
sam deploy --guided
```

`--guided` walks you through every parameter. Accept these answers for a clean first deploy:

| Prompt | Answer |
|---|---|
| Stack Name | `pitstop-analytics` |
| AWS Region | `ap-southeast-2` |
| Parameter `Environment` | `dev` |
| Parameter `EnablePhase2` | `false` *(see note below)* |
| Parameter `LogRetentionDays` | `30` |
| Confirm changes before deploy | **Y** |
| Allow SAM CLI IAM role creation | **Y** |
| Disable rollback | **N** |
| Save arguments to configuration file | **Y** |
| SAM configuration file | `samconfig.toml` |
| SAM configuration environment | `default` |

> **Why EnablePhase2=false on the first deploy:** Phase 2 provisions a SageMaker execution role and 3 extra Lambdas you don't need yet. Get Phase 1 healthy, ingest a race, watch the dashboard render — *then* flip Phase 2 on with `make deploy-phase2` (step 8).

You'll see CloudFormation events stream as the stack creates. First deploy takes **8–12 min** because CloudFront takes the longest to provision.

When it finishes, note the outputs:

```bash
aws cloudformation describe-stacks --stack-name pitstop-analytics \
  --query "Stacks[0].Outputs" --output table
```

You want `ApiEndpoint`, `DashboardUrl`, `DashboardBucketName`, `DashboardDistributionId`.

---

## 5. Ingest your first race

The schedule fires every Monday at 06:00 UTC, but for the first deploy you'll trigger it manually so you can see data flow end-to-end.

```bash
aws lambda invoke \
  --function-name pitstop-ingestion-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"year": 2024, "round": 5}' \
  --region ap-southeast-2 \
  /tmp/ingestion-response.json

cat /tmp/ingestion-response.json | jq .
```

Expected response:

```json
{
  "statusCode": 200,
  "body": {
    "year": 2024,
    "round": 5,
    "manifest_key": "races/2024/5/_manifest.json"
  }
}
```

The S3 `Object Created` event for the manifest will trigger the processor automatically. Watch it via CloudWatch:

```bash
aws logs tail /aws/lambda/pitstop-processor-dev --since 5m --follow
```

When you see `wrote N items to F1Data`, the round is processed.

---

## 6. Deploy the dashboard

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name pitstop-analytics \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardBucketName'].OutputValue" --output text)
DIST=$(aws cloudformation describe-stacks --stack-name pitstop-analytics \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardDistributionId'].OutputValue" --output text)

aws s3 sync frontend/ "s3://$BUCKET/" --delete --exclude "*.md"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```

Then open the dashboard:

```bash
aws cloudformation describe-stacks --stack-name pitstop-analytics \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text
```

Cmd-click the URL. You should see the 2024 season hub with the round you just ingested.

> **Note:** the dashboard's `config.js` defaults to `apiBase = "/api"` in production. CloudFront isn't pre-wired to forward `/api/*` to API Gateway — for the first deploy, edit `frontend/src/config.js` and set `PRODUCTION_API` to the actual `ApiEndpoint` URL from step 4, then re-sync.

---

## 7. Backfill historical data (optional but recommended)

Before flipping Phase 2 on, you want at least 2 full seasons of historical data so the fingerprint engine has something to work with.

```bash
python scripts/seed_historical.py --start 2022 --end 2024
```

This iterates every round in those seasons, invokes the deployed ingestion Lambda, and waits 2s between rounds to be polite to the upstream APIs. Takes ~30 min for 3 seasons.

**Cheaper alternative** — run the handler locally without going through Lambda:

```bash
python scripts/seed_historical.py --start 2022 --end 2024 --local
```

Local mode bypasses Lambda billing but still hits FastF1 + Ergast.

---

## 8. Enable Phase 2

```bash
make deploy-phase2
```

That target doesn't exist yet — add it now:

```bash
echo 'deploy-phase2:' >> Makefile
echo '	sam deploy --no-confirm-changeset --parameter-overrides Environment=dev EnablePhase2=true' >> Makefile
```

Or just run the underlying command directly:

```bash
sam deploy --no-confirm-changeset \
  --parameter-overrides Environment=dev EnablePhase2=true
```

This adds the SharedLayer, the fingerprint/trainer/predictor Lambdas, the SageMaker execution role, and the Thursday-12:00-UTC + monthly schedules.

Trigger the fingerprint Lambda for a round you've ingested:

```bash
aws lambda invoke \
  --function-name pitstop-fingerprint-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"year": 2024, "round": 5}' \
  --region ap-southeast-2 \
  /tmp/fingerprint-response.json
```

---

## 9. Wire up GitHub Actions (one-time, optional)

The two workflows in `.github/workflows/` expect:

1. An IAM role in your account with a trust policy for GitHub's OIDC provider.
2. The role ARN saved as `AWS_DEPLOY_ROLE_ARN` in your repo's Actions secrets.

Quickest setup using AWS-managed templates:

```bash
# 1. Add GitHub as an OIDC IdP (one-time per account)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

Then create a role with this trust policy (replace `YOUR_ORG/YOUR_REPO`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"}
    }
  }]
}
```

Attach managed policies (`PowerUserAccess` is fine for `dev`; tighten for prod). Save the role ARN as a GitHub Actions secret named `AWS_DEPLOY_ROLE_ARN`.

After that, every push to `main` deploys.

---

## Tearing it all down

If you want to remove every resource (S3 buckets are `Retain`-protected — you'll need to empty them first):

```bash
# Empty retain-protected buckets
for b in pitstop-raw pitstop-processed pitstop-models pitstop-dashboard; do
  aws s3 rm "s3://$b-$(aws sts get-caller-identity --query Account --output text)" --recursive
done

aws cloudformation delete-stack --stack-name pitstop-analytics
aws cloudformation wait stack-delete-complete --stack-name pitstop-analytics
```

---

## Costs to expect

Dev environment, idle (no scheduled invocations firing): **~$0.50–$1.00 / month** dominated by CloudFront's price-class-100 minimums and DynamoDB on-demand baseline.

Active (Monday ingestion + Thursday predictions + monthly retrain): **~$3–$6 / month**. The single biggest line item is the monthly SageMaker training job (~$0.10/run on `ml.m5.large` for 5–10 min).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `sam build` fails on `fastf1` install | Use `sam build --use-container` (needs Docker running) |
| Ingestion Lambda times out | First-ever invocation downloads ~50MB into the FastF1 cache; subsequent runs are fast |
| Processor never runs after ingestion | Check EventBridge rule `IngestionFunction-S3RawDataCreated` is `ENABLED`; check S3 bucket has `EventBridgeConfiguration` enabled |
| Dashboard shows "Could not load" | `config.js` still points to `/api`; edit and re-sync (see step 6 note) |
| `make preflight` fails on Python deps | Activate the venv: `source .venv/bin/activate` |

When you hit something not in the table, paste the CloudWatch error in chat and I'll diagnose.
