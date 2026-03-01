import os
import time
import json
import smtplib
import glob
import boto3
from email.message import EmailMessage

# --- Configuration ---
LOG_DIR = "/var/log"
CACHE_FILE = "/app/error_cache.json"

# Expanded Trigger Codes
ERROR_CODES = [
    "500", "502", "503", "504", "401", "403", "429",  # HTTP/API
    "FATAL", "CRITICAL", "PANIC", "EXCEPTION", "ERROR", # Severity
    "OUT OF MEMORY", "CONNECTION REFUSED", "TIMEOUT"   # System
]

# Exclusion Keywords (Noise Reduction)
IGNORE_KEYWORDS = [
    "favicon.ico", "Googlebot", "status check success", "health-check"
]

# Bedrock Config (Boto3 automatically uses AWS_BEARER_TOKEN_BEDROCK)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
bedrock = boto3.client(service_name="bedrock-runtime", region_name=AWS_REGION)

# Email Credentials
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Global trackers
file_positions = {}
error_cache = {}

def load_cache():
    global error_cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            error_cache = json.load(f)

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(error_cache, f)

def send_alert(error_line, solution):
    msg = EmailMessage()
    msg.set_content(f"Log Error Detected:\n{error_line}\n\nTroubleshooting Suggestion:\n{solution}")
    msg['Subject'] = "ALERT: Server Error Detected"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print(f"✅ Email notification sent for error.")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def get_ai_troubleshooting(error_line):
    if error_line in error_cache:
        print("♻️  Using cached solution.")
        return error_cache[error_line]
    
    print("🧠 Consulting Amazon Bedrock...")
    model_id = "us.amazon.nova-lite-v1:0"
    prompt = f"Analyze this server log error and provide a concise fix: {error_line}"
    
    try:
        response = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 500, "temperature": 0.5}
        )
        # FIX: The response content is a LIST of blocks; access index [0] first
        solution = response['output']['message']['content'][0]['text']
    except Exception as e:
        print(f"❌ Bedrock error: {e}")
        solution = f"AI Analysis failed: {e}"

    error_cache[error_line] = solution
    save_cache()
    return solution

def monitor_logs():
    print(f"🔍 Monitoring {LOG_DIR} for {len(ERROR_CODES)} triggers (Case-Insensitive)...")
    
    while True:
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        
        for filepath in log_files:
            if filepath not in file_positions:
                file_positions[filepath] = os.path.getsize(filepath)
                continue

            current_size = os.path.getsize(filepath)
            if current_size < file_positions[filepath]:
                file_positions[filepath] = 0

            with open(filepath, "r") as f:
                f.seek(file_positions[filepath])
                lines = f.readlines()
                file_positions[filepath] = f.tell()

                for line in lines:
                    clean_line = line.strip()
                    upper_line = clean_line.upper()

                    # Filter: Skip if noisy
                    if any(noise.upper() in upper_line for noise in IGNORE_KEYWORDS):
                        continue

                    # Filter: Trigger if error found
                    if any(code in upper_line for code in ERROR_CODES):
                        solution = get_ai_troubleshooting(clean_line)
                        send_alert(clean_line, solution)

        time.sleep(2)

if __name__ == "__main__":
    load_cache()
    monitor_logs()
