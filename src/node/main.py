from node.service import run_service


def main():
    """Główny punkt wejścia (Entry Point) aplikacji Node.

    Uruchamia główną usługę Node (pystray tray, Worker LLM i Satelitę).
    """
    run_service()


if __name__ == "__main__":
    main()
