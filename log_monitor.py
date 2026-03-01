import os
import time
import json
import hashlib
import glob
import smtplib
import re
import base64
import datetime
import boto3
from email.message import EmailMessage

# --- Configuration & Environment Variables ---
LOG_DIR = os.getenv("LOG_DIR", "/var/log")
CACHE_FILE = os.getenv("CACHE_FILE", "/app/data/error_cache.json")
STATE_FILE = os.getenv("STATE_FILE", "/app/data/log_state.json")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "5")) # Default 5 seconds

# REGEX TRIGGER
ERROR_PATTERNS = [
    r"HTTP/1\.\d\s5\d{2}",
    r"\b(FATAL|CRITICAL|PANIC|ERROR)\b",
    r"OUT\sOF\sMEMORY",
    r"CONNECTION\s(REFUSED|TIMEOUT)",
    r"EXCEPTION:\s\w+"
]
TRIGGER_RE = re.compile("|".join(ERROR_PATTERNS), re.IGNORECASE)
IGNORE_KEYWORDS = ["favicon.ico", "Googlebot", "health-check", "status check success"]

# Secrets & AWS
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = "us.amazon.nova-lite-v1:0"
TOKEN = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

bedrock = boto3.client(service_name="bedrock-runtime", region_name=AWS_REGION)

# Global State
log_state = {"files": {}, "last_expiry_alert": 0} 
error_cache = {}

def load_persistence():
    global error_cache, log_state
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f: error_cache = json.load(f)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: 
            data = json.load(f)
            log_state.update(data)

def save_persistence():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f: json.dump(error_cache, f)
    with open(STATE_FILE, "w") as f: json.dump(log_state, f)

def send_alert(subject, body):
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print(f"🚀 Email sent: {subject}")
    except Exception as e:
        print(f"❌ SMTP Failure: {e}")

def check_token_health():
    """Daily email alert starting 7 days before Bedrock Token expiry."""
    if not TOKEN or "." not in TOKEN: return
    try:
        parts = TOKEN.split('.')
        if len(parts) < 2: return
        payload_data = parts[1]
        payload_data += '=' * (4 - len(payload_data) % 4)
        payload = json.loads(base64.b64decode(payload_data).decode("utf-8"))
        
        if "exp" in payload:
            exp_ts = payload["exp"]
            exp_date = datetime.datetime.fromtimestamp(exp_ts, tz=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days_left = (exp_date - now).days
            
            if days_left <= 7:
                now_ts = time.time()
                if (now_ts - log_state.get("last_expiry_alert", 0)) >= 86400:
                    subject = f"⚠️ ACTION REQUIRED: Bedrock Token Expires in {max(0, days_left)} Days"
                    body = f"Token expires on {exp_date.strftime('%Y-%m-%d')}. Rotate in OCP Secret."
                    send_alert(subject, body)
                    log_state["last_expiry_alert"] = now_ts
                    save_persistence()
    except Exception as e:
        print(f"ℹ️ Token check error: {e}")

def get_ai_analysis(error_line):
    line_hash = hashlib.sha256(error_line.encode()).hexdigest()
    if line_hash in error_cache: return error_cache[line_hash]
    
    prompt = f"Analyze: '{error_line}'. If critical, 2-line fix. Else, respond ONLY with 'IGNORE'."
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 250, "temperature": 0}
        )
        solution = response['output']['message']['content'][0]['text']
        error_cache[line_hash] = solution
        save_persistence()
        return solution
    except Exception as e: return f"AI Unavailable: {e}"

def monitor_logs():
    print(f"📡 Monitoring {LOG_DIR} every {SCAN_INTERVAL}s...")
    while True:
        check_token_health()
        for filepath in glob.glob(os.path.join(LOG_DIR, "*.log")):
            try:
                f_stat = os.stat(filepath)
                inode = str(f_stat.st_ino)
                if inode not in log_state["files"]:
                    log_state["files"][inode] = f_stat.st_size
                    continue
                last_pos = log_state["files"][inode]
                if f_stat.st_size < last_pos: last_pos = 0 

                with open(filepath, "r") as f:
                    f.seek(last_pos)
                    for line in f:
                        clean = line.strip()
                        if not clean or any(n.upper() in clean.upper() for n in IGNORE_KEYWORDS):
                            continue
                        if TRIGGER_RE.search(clean):
                            analysis = get_ai_analysis(clean)
                            if "IGNORE" not in analysis.upper():
                                send_alert("🔴 ALERT: Log Error", f"Error: {clean}\n\nFix: {analysis}")
                    log_state["files"][inode] = f.tell()
                save_persistence()
            except Exception as e: print(f"⚠️ Error: {e}")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    load_persistence()
    monitor_logs()
