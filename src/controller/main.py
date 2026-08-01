import logging

logging.basicConfig(level=logging.INFO)

def start():
    """Entry point dla CLI (regis-controller)."""
    import uvicorn
    uvicorn.run("controller.app:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start()