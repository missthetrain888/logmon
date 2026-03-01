FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script
COPY log_monitor.py .

# Run unbuffered so logs appear in OCP console immediately
CMD ["python", "-u", "log_monitor.py"]
