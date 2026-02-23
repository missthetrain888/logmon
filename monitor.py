import os
import time
import json
import smtplib
import glob
from email.message import EmailMessage
from google import genai

# --- Configuration from Environment ---
LOG_DIR = "/var/log"
ERROR_CODES = ["401", "500"]
CACHE_FILE = "/app/error_cache.json"

# Credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") # 16-char App Password
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Initialize Gemini Client (Modern SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

# Global trackers
file_positions = {}  # {filepath: last_read_byte}
error_cache = {}     # {error_string: ai_solution}

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
    msg['Subject'] = f"ALERT: Server Error Detected"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    try:
        # Port 587 with STARTTLS is the modern standard for Gmail
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print(f"✅ Email notification sent for: {error_line[:30]}...")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def get_ai_troubleshooting(error_line):
    if error_line in error_cache:
        print("♻️  Duplicate error. Using cached solution.")
        return error_cache[error_line]
    
    print("🧠 New error. Consulting Gemini AI...")
    prompt = f"Analyze this server log error and provide a concise fix: {error_line}"
    
    response = client.models.generate_content(
        model="gemini-2.5-flash", 
        contents=prompt
    )
    solution = response.text
    
    # Update cache
    error_cache[error_line] = solution
    save_cache()
    return solution

def monitor_logs():
    print(f"🔍 Monitoring all .log files in {LOG_DIR} for errors: {ERROR_CODES}...")
    
    while True:
        # Find all .log files
        log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
        
        for filepath in log_files:
            # Initialize new files at the end to avoid processing old history
            if filepath not in file_positions:
                file_positions[filepath] = os.path.getsize(filepath)
                continue

            # Check if file was truncated/rotated
            current_size = os.path.getsize(filepath)
            if current_size < file_positions[filepath]:
                file_positions[filepath] = 0

            with open(filepath, "r") as f:
                f.seek(file_positions[filepath])
                lines = f.readlines()
                file_positions[filepath] = f.tell() # Re-sync pointer

                for line in lines:
                    clean_line = line.strip()
                    if any(code in clean_line for code in ERROR_CODES):
                        solution = get_ai_troubleshooting(clean_line)
                        send_alert(clean_line, solution)

        time.sleep(2) # Polling interval for Windows volume stability

if __name__ == "__main__":
    load_cache()
    monitor_logs()
