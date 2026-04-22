from flask import Flask
from threading import Thread
import time
import urllib.request
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def self_ping():
    time.sleep(30)
    domain = os.getenv("REPLIT_DEV_DOMAIN") or "localhost:8080"
    url = f"https://{domain}" if not domain.startswith("http") else domain
    while True:
        try:
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            pass
        time.sleep(180)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

    p = Thread(target=self_ping)
    p.daemon = True
    p.start()
