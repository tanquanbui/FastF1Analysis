FROM public.ecr.aws/lambda/python:3.11

# Build context is the repo root so we can include shared/ alongside the
# function code. See template.yaml DockerContext / Dockerfile metadata.

COPY functions/predictor/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY functions/predictor/*.py ${LAMBDA_TASK_ROOT}/
COPY shared/python/*.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
