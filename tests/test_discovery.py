import logging
from protocol.discovery import discover_controller

logging.basicConfig(level=logging.INFO)
print("Rozpoczynam wyszukiwanie...")
try:
    url = discover_controller(timeout=2)
    print("Znaleziono:", url)
except Exception as e:
    print("Błąd:", e)
print("Koniec.")
