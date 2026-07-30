import os
import urllib.request
import zipfile
import logging

logging.basicConfig(level=logging.INFO)

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip"
MODEL_DIR = os.path.join("data", "models")
VOSK_DIR = os.path.join(MODEL_DIR, "vosk")
ZIP_PATH = os.path.join(MODEL_DIR, "vosk-model-small-pl.zip")

def main():
    os.makedirs(VOSK_DIR, exist_ok=True)
    
    if os.path.exists(os.path.join(VOSK_DIR, "am")):
        logging.info("Model Vosk już istnieje. Pomijam pobieranie.")
        return

    logging.info(f"Pobieranie modelu Vosk (Small PL) z {MODEL_URL}...")
    urllib.request.urlretrieve(MODEL_URL, ZIP_PATH)
    
    logging.info("Rozpakowywanie modelu...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        # Rozpakowujemy do tymczasowego folderu
        zip_ref.extractall(MODEL_DIR)
        
    extracted_folder = os.path.join(MODEL_DIR, "vosk-model-small-pl-0.22")
    if os.path.exists(extracted_folder):
        import shutil
        for item in os.listdir(extracted_folder):
            shutil.move(os.path.join(extracted_folder, item), VOSK_DIR)
        os.rmdir(extracted_folder)
        
    os.remove(ZIP_PATH)
    logging.info(f"Model Vosk gotowy w {VOSK_DIR}")

if __name__ == "__main__":
    main()
