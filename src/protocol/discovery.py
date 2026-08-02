import socket
import logging
import threading
import time

DISCOVERY_PORT = 8002
PING_MSG = b"REGIS_DISCOVERY_PING"

def start_discovery_server(controller_url: str) -> threading.Thread:
    logging.debug("start_discovery_server CALLED")
    def _listen():
        logging.debug("Discovery UDP THREAD STARTED")
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(("", DISCOVERY_PORT))
                logging.info(f"Serwer UDP Auto-Discovery uruchomiony na porcie {DISCOVERY_PORT}")
                
                while True:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if data == PING_MSG:
                            logging.debug(f"[Discovery] Otrzymano ping od {addr}. Odsyłam adres: {controller_url}")
                            sock.sendto(controller_url.encode('utf-8'), addr)
                    except Exception as e:
                        logging.warning(f"Błąd przetwarzania pakietu UDP Discovery: {e}")
                        time.sleep(1)
            except Exception as e:
                logging.error(f"CRITICAL UDP ERROR w nasłuchiwaniu (błąd bindowania/gniazda): {e}. Próba restartu za 5 sekund...")
                time.sleep(5)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    return t

def get_broadcast_addresses():
    addresses = ["255.255.255.255", "<broadcast>"]
    try:
        host_name = socket.gethostname()
        ips = socket.gethostbyname_ex(host_name)[2]
        for ip in ips:
            parts = ip.split('.')
            if len(parts) == 4:
                parts[3] = '255'
                addresses.append('.'.join(parts))
    except Exception:
        pass
    return list(set(addresses))

def discover_controller(timeout: int = 5) -> str:
    """
    Wysyła broadcast UDP do sieci lokalnej w celu znalezienia Kontrolera.
    Zwraca URL kontrolera (np. 'http://192.168.1.50:8000') lub rzuca wyjątek po przekroczeniu czasu.
    """
    logging.info("Wysyłam zapytanie Auto-Discovery w poszukiwaniu Kontrolera (na wszystkie interfejsy)...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    
    try:
        bcasts = get_broadcast_addresses()
        for bcast in bcasts:
            try:
                sock.sendto(PING_MSG, (bcast, DISCOVERY_PORT))
            except Exception:
                pass # Ignoruj błędy dla niedostępnych interfejsów
                
        # Oczekujemy na odpowiedź. Zbierze pierwszą pasującą, co oznacza najszybszą ścieżkę do serwera.
        start_time = time.time()
        while True:
            # Ponieważ pętla może odebrać kilka pakietów z echem, sprawdzamy timeout manualnie
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                raise socket.timeout()
            sock.settimeout(remaining)
            
            data, addr = sock.recvfrom(1024)
            
            controller_url = data.decode('utf-8').strip()
            if controller_url.startswith("http"):
                logging.info(f"Sukces! Odnaleziono Kontroler pod adresem: {controller_url} (odpowiedź z {addr[0]})")
                return controller_url
    except socket.timeout:
        msg = f"Auto-Discovery timeout: Nie udało się odnaleźć Kontrolera w sieci w ciągu {timeout} sekund."
        logging.error(msg)
        raise RuntimeError(msg)
    except Exception as e:
        logging.error(f"Błąd podczas Auto-Discovery: {e}")
        raise
    finally:
        sock.close()

def get_local_ip() -> str:
    """Pobiera lokalny adres IP w sieci domowej."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

