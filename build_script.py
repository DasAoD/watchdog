import subprocess
import os
import shutil
import sys
import time # Importiere das time-Modul für Zeitstempel und sleep
from tqdm import tqdm # Importiere tqdm
from datetime import datetime # Importiere datetime für Zeitstempel im Dateinamen

# Konfiguration
SPEC_FILE = "watchdog.spec"
APP_NAME = "Watchdog"
RELEASE_FOLDER_NAME = f"{APP_NAME}"
EXE_NAME_IN_DIST = f"{APP_NAME}.exe"
LOG_FOLDER_NAME = "log" # Name für den Log-Ordner

# Definiere grobe Phasen des PyInstaller-Prozesses und ihre geschätzte "Gewichtung"
PYINSTALLER_PHASES = {
    "Analyzing modules for base_library.zip": 10,
    "Analyzing": 20, 
    "Looking for Python shared library": 5,
    "Processing module hooks": 5,
    "Performing binary vs. data reclassification": 5,
    "Analyzing run-time hooks": 5,
    "Creating base_library.zip": 10,
    "Looking for dynamic libraries": 5,
    "Building PYZ": 10,
    "Building PKG": 15, 
    "Building EXE": 10, 
    "Build complete!": 5 
}
# Erstelle eine Kopie für jeden Lauf, da wir die Gewichte verbrauchen
current_phases_weights = {} 
TOTAL_WEIGHT = sum(PYINSTALLER_PHASES.values())

def run_command_with_progress_and_logging(command_list, log_file_path):
    """Führt einen Befehl aus, loggt die Ausgabe und versucht, den Fortschritt darzustellen."""
    global current_phases_weights # Um die Gewichte für den aktuellen Lauf zu nutzen/modifizieren
    current_phases_weights = PYINSTALLER_PHASES.copy() # Für jeden Lauf eine frische Kopie

    # Öffne die Logdatei im Schreibmodus (append, 'a', falls du Logs von mehreren Läufen sammeln willst)
    with open(log_file_path, 'w', encoding='utf-8') as lf:
        lf.write(f"--- Log für PyInstaller-Build gestartet um {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        lf.write(f"Befehl: {' '.join(command_list)}\n\n")
        
        process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        
        with tqdm(total=TOTAL_WEIGHT, unit="step", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
            pbar.set_description("PyInstaller Build")
            current_progress = 0
            
            for line in iter(process.stdout.readline, ''):
                lf.write(line) # Schreibe jede Zeile von PyInstaller ins Logfile
                # print(line.strip()) # Optional: Original-PyInstaller-Ausgabe auch auf Konsole anzeigen

                for phase_keyword, weight in list(current_phases_weights.items()): # list() für sichere Iteration bei Modifikation
                    if phase_keyword in line and weight > 0: # Nur wenn Gewicht > 0
                        advance = min(weight, TOTAL_WEIGHT - current_progress)
                        if advance > 0:
                            pbar.update(advance)
                            current_progress += advance
                            current_phases_weights[phase_keyword] = 0 # "Verbrauche" das Gewicht
                        break 
                if process.poll() is not None:
                    break
            
            if current_progress < TOTAL_WEIGHT and process.returncode == 0:
                pbar.update(TOTAL_WEIGHT - current_progress)
                
        process.stdout.close()
        return_code = process.wait()
        
        lf.write(f"\n--- PyInstaller-Build beendet um {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} mit Return Code: {return_code} ---\n")
        return return_code

def main_build():
    # Log-Ordner erstellen, falls nicht vorhanden
    if not os.path.exists(LOG_FOLDER_NAME):
        os.makedirs(LOG_FOLDER_NAME)
        print(f"Log-Ordner '{LOG_FOLDER_NAME}' erstellt.")

    # Log-Dateiname mit Zeitstempel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_name = f"pyinstaller_build_{timestamp}.log"
    log_file_path = os.path.join(LOG_FOLDER_NAME, log_file_name)
    
    print_colored(f"Beginne mit der Erstellung der {EXE_NAME_IN_DIST}...", "yellow_black")
    print_colored(f"Alle Ausgaben von PyInstaller werden in '{log_file_path}' gespeichert.", "cyan")
    print("-" * 50)

    pyinstaller_command = ["pyinstaller", SPEC_FILE]
    # Wenn du den Log-Level für die Konsolenausgabe (die wir hier umleiten) reduzieren willst:
    # pyinstaller_command.insert(1, "--log-level")
    # pyinstaller_command.insert(2, "WARN") # Oder ERROR
    
    return_code = run_command_with_progress_and_logging(pyinstaller_command, log_file_path)

    print("-" * 50)
    if return_code != 0:
        print_colored(f"PyInstaller-Build fehlgeschlagen! (Return Code: {return_code})", "red")
        print_colored(f"Details siehe Logdatei: '{log_file_path}'", "yellow")
        print_colored("build und dist Ordner werden nicht gelöscht.", "yellow")
        sys.exit(1) # Beende das Skript mit einem Fehlercode

    print_colored("PyInstaller-Build erfolgreich.", "green")
    print("Verschiebe Watchdog.exe und räume auf...")

    # Release-Ordner erstellen
    if not os.path.exists(RELEASE_FOLDER_NAME):
        os.makedirs(RELEASE_FOLDER_NAME)

    source_exe_path = os.path.join("dist", EXE_NAME_IN_DIST)
    target_exe_path = os.path.join(RELEASE_FOLDER_NAME, EXE_NAME_IN_DIST)

    if os.path.exists(source_exe_path):
        try:
            shutil.move(source_exe_path, target_exe_path)
            print(f"{EXE_NAME_IN_DIST} nach {RELEASE_FOLDER_NAME} verschoben.")
        except Exception as e_move:
            print_colored(f"FEHLER beim Verschieben der {EXE_NAME_IN_DIST}: {e_move}", "red")
            print_colored(f"Die .exe befindet sich möglicherweise noch in '{source_exe_path}'.", "yellow")
    else:
        print_colored(f"WARNUNG: {EXE_NAME_IN_DIST} nicht im dist-Ordner gefunden!", "red")
        print_colored(f"Überprüfe die Logdatei '{log_file_path}' auf Fehler während des Builds.", "yellow")


    # Aufräumen (nur wenn Verschieben erfolgreich war oder .exe nicht existierte)
    # oder immer aufräumen, je nach Präferenz
    if os.path.exists("build"):
        print("Lösche build-Ordner...")
        shutil.rmtree("build", ignore_errors=True) # ignore_errors=True für mehr Robustheit
    if os.path.exists("dist"):
        print("Lösche dist-Ordner...")
        shutil.rmtree("dist", ignore_errors=True) # ignore_errors=True

    print("Aufräumen abgeschlossen.")
    print_colored(f"Die fertige .exe liegt nun im Ordner '{RELEASE_FOLDER_NAME}' bereit.", "green_black")
    print_colored(f"Ein detailliertes Build-Log wurde gespeichert unter: '{log_file_path}'", "cyan")
    
    try:
        wait_seconds = 3
        print(f"\nDas Fenster schließt sich in {wait_seconds} Sekunden...")
        time.sleep(wait_seconds)
    except KeyboardInterrupt:
        print("\nWarten abgebrochen.")

def print_colored(text, color_key="normal"):
    # ... (deine print_colored Funktion bleibt gleich) ...
    colors = {
        "red": ("Red", None), "green": ("Green", None), "yellow": ("Yellow", None),
        "cyan": ("Cyan", None), "yellow_black": ("Black", "DarkYellow"),
        "green_black": ("Black", "Green"), "normal": (None, None)
    }
    fg, bg = colors.get(color_key, (None, None))
    if os.name == 'nt':
        try:
            command = f"Write-Host -NoNewline '{text}'" # -NoNewline für einzelne Zeile
            if fg: command += f" -ForegroundColor {fg}"
            if bg: command += f" -BackgroundColor {bg}"
            command += "; Write-Host ''" # Fügt einen Zeilenumbruch am Ende hinzu
            subprocess.run(["powershell", "-Command", command], check=True, shell=True)
            return
        except Exception: pass
    print(text)

if __name__ == "__main__":
    if os.name == 'nt':
        try:
            subprocess.run(["chcp", "65001"], capture_output=True, check=True, shell=True)
        except Exception as e:
            print(f"Hinweis: Konnte Codepage nicht auf 65001 setzen: {e}")
    main_build()