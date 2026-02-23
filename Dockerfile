FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir google-generativeai

# Copy script
COPY monitor.py .

# Create log directory to be mounted
RUN mkdir -p /var/log && touch /var/log/server.log

CMD ["python", "monitor.py"]
