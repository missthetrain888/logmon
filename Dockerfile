FROM python:3.11-slim

WORKDIR /app

# Install modern Gemini SDK
RUN pip install --no-cache-dir google-genai

COPY monitor.py .

# Ensure the log directory exists
RUN mkdir -p /var/log

CMD ["python", "monitor.py"]
