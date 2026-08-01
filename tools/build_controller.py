import os
import subprocess
import sys
import shutil

def deploy_to_pi():
    print("========================================================")
    print("      Szybki Deployment (ZIP) na serwer główny (Raspberry Pi)")
    print("========================================================\n")
    
    server = "theblok@192.168.0.119"
    remote_dir = "/home/theblok/regis"
    
    print("1. Zatrzymywanie Kontrolera na Raspberry Pi...")
    subprocess.run(["ssh", "-t", server, "sudo timeout 5 systemctl stop regis.service || sudo systemctl kill --signal=SIGKILL regis.service || true"])
    
    print("2. Pakowanie kodu źródłowego i logiki do archiwum ZIP na Windowsie...")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    os.makedirs("dist", exist_ok=True)
    
    temp_dir = "dist/regis_temp"
    os.makedirs(temp_dir)
    
    # Skupiamy się na pakowaniu czystego kodu oraz stałych promptów i konfiguracji
    shutil.copytree("src", os.path.join(temp_dir, "src"))
    if os.path.exists("config"):
        shutil.copytree("config", os.path.join(temp_dir, "config"))
    
    if os.path.exists("requirements.txt"):
        shutil.copy("requirements.txt", temp_dir)
    if os.path.exists("pyproject.toml"):
        shutil.copy("pyproject.toml", temp_dir)
    
    zip_base = "dist/regis_update"
    shutil.make_archive(zip_base, "zip", root_dir=temp_dir)
    zip_file = f"{zip_base}.zip"
    shutil.rmtree(temp_dir)
    
    print(f"3. Wysyłanie archiwum {zip_file} przez SCP na malinkę...")
    result = subprocess.run(["scp", zip_file, f"{server}:{remote_dir}/regis_update.zip"])
    if result.returncode != 0:
        print("[BŁĄD] Wystąpił błąd podczas wysyłania archiwum przez SCP.")
        sys.exit(1)
        
    print("4. Czyszczenie starych plików na malince (reset logiki) i rozpakowywanie archiwum...")
    # Tutaj realizujemy zalecenie: wrażliwe dane, historia, .venv zostają na miejscu!
    # Usuwamy całkowicie TYLKO starą logikę (src/), stałe prompty i ewentualne stare rozpakowane śmieci kółek.
    ssh_cmd = [
        "ssh", "-t", server,
        f"cd {remote_dir} && "
        f"rm -rf src/ config/ controller/ core/ integrations/ node/ && "
        f"unzip -q -o regis_update.zip && "
        f"rm regis_update.zip && "
        f"source .venv/bin/activate && "
        f"pip install --no-cache-dir -e '.[controller]' && "
        f"echo '5. Odbudowa demona i restartowanie Kontrolera...' && "
        f"sudo systemctl daemon-reload && "
        f"sudo systemctl restart regis.service && "
        f"echo '\\n[Status Regis Controller]' && systemctl status regis.service --no-pager | grep Active"
    ]
    result = subprocess.run(ssh_cmd)
    if result.returncode != 0:
        print("[BŁĄD] Wystąpił błąd podczas czyszczenia, rozpakowywania lub uruchamiania usług na malince.")
        sys.exit(1)

    print("\n========================================================")
    print("SUKCES! Logika i prompty zostały zainstalowane od zera, usługi działają!")
    print("========================================================\n")

if __name__ == "__main__":
    deploy_to_pi()
