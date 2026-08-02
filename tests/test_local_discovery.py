import time
import logging
from protocol.discovery import start_discovery_server, discover_controller

logging.basicConfig(level=logging.INFO)

print("Uruchamiam lokalny serwer testowy...")
start_discovery_server("http://127.0.0.1:8000")
time.sleep(1)

print("Szukam kontrolera lokalnie...")
try:
    url = discover_controller(timeout=2)
    print("ZNALEZIONO:", url)
except Exception as e:
    print("BŁĄD:", e)
