FROM public.ecr.aws/lambda/python:3.11

# Install deps first for better build caching.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# App code.
COPY *.py ${LAMBDA_TASK_ROOT}/

# Lambda invokes app.handler from LAMBDA_TASK_ROOT (default behavior).
CMD ["app.handler"]
