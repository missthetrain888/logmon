FROM python:3.12-slim

WORKDIR /app

# Install AWS SDK (Boto3) for Bedrock support
RUN pip install --no-cache-dir boto3>=1.35.69

COPY monitor.py .

# Ensure the log directory exists
RUN mkdir -p /var/log

# The script requires AWS_BEARER_TOKEN_BEDROCK and AWS_REGION to be set at runtime
CMD ["python", "monitor.py"]
