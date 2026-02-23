import os
import time
import json
import smtplib
from email.message import EmailMessage
import google.generativeai as genai

# Configuration from Environment Variables
LOG_FILE = "/var/log/server.log"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = "smtp.gmail.com"  # Example for Gmail
ERROR_CODES = ["401", "500"]

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Simple Cache for Duplicate Errors
cache_file = "error_cache.json"
if os.path.exists(cache_file):
    with open(cache_file, "r") as f:
        error_cache = json.load(f)
else:
    error_cache = {}

def send_alert(error_line, solution):
    msg = EmailMessage()
    msg.set_content(f"Error Detected: {error_line}\n\nTroubleshooting Info:\n{solution}")
    msg['Subject'] = f"Server Alert: {error_line[:20]}..."
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

def process_log_line(line):
    if any(code in line for code in ERROR_CODES):
        # Use line as unique key for exact duplicates
        if line in error_cache:
            print("Repeated error found. Sending cached solution.")
            send_alert(line, error_cache[line])
        else:
            print("New error found. Consulting Gemini...")
            prompt = f"Troubleshoot this server log error and provide a fix: {line}"
            response = model.generate_content(prompt)
            solution = response.text
            
            # Cache and Notify
            error_cache[line] = solution
            with open(cache_file, "w") as f:
                json.dump(error_cache, f)
            send_alert(line, solution)

def tail_f(filename):
    with open(filename, "r") as f:
        f.seek(0, 2)  # Go to end of file
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            process_log_line(line.strip())

if __name__ == "__main__":
    print(f"Monitoring {LOG_FILE} for errors: {ERROR_CODES}...")
    tail_f(LOG_FILE)
