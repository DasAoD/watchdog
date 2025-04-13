# -*- coding: utf-8 -*-
import configparser
import os
import time
import psutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkFont
import threading

def resource_path(relative_path):
    """ Ermittelt den korrekten Pfad für Ressourcen (im Skript oder in PyInstaller Bundle). """
    try:
        # PyInstaller erstellt einen Temp-Ordner und speichert Pfad in _MEIPASS
        base_path = sys._MEIPASS
        # print(f"INFO: Läuft aus PyInstaller Temp-Ordner: {base_path}")
    except Exception:
        # _MEIPASS nicht vorhanden? Läuft als normales .py Skript.
        # Verwende den Pfad, den wir am Anfang ermittelt haben
        base_path = application_path # Greift auf globale Variable zu
        # print(f"INFO: Läuft als Skript, Basis-Pfad: {base_path}")

    path = os.path.join(base_path, relative_path)
    # print(f"INFO: Resource Path für '{relative_path}': {path}")
    return path

# --- Konstanten und globale Variablen ---
try:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        application_path = os.path.dirname(sys.executable)
        IS_BUNDLED = True
    else:
        application_path = os.path.dirname(os.path.realpath(__file__))
        IS_BUNDLED = False
    CONFIG_FILE = os.path.join(application_path, 'watchdog.ini')
except Exception as e:
    print(f"FEHLER: Konnte Anwendungspfad nicht bestimmen: {e}")
    application_path = os.getcwd() # Fallback
    CONFIG_FILE = os.path.join(application_path, 'watchdog.ini')
    IS_BUNDLED = False

DEFAULT_CHECK_CYCLE_SEC = 60
DEFAULT_START_DELAY_SEC = 15
DEBUG_MODE = False # <<< Auf False gesetzt für weniger Konsolenausgabe! Bei Bedarf auf True setzen.
SHORT_ADLIB_INTERVAL_SEC = 1.0

# Globale Variablen
config = configparser.ConfigParser(inline_comment_prefixes=('#',';'), interpolation=None)
program_list = []
check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC
start_delay_sec = DEFAULT_START_DELAY_SEC
program_count = 0
is_running = False
watchdog_thread = None
stop_event = None

watchdog_state = 0
last_check_completion_time = 0.0
last_program_start_time = 0.0
current_program_index = 0

root = None; check_cycle_var_sec = None; start_delay_var_sec = None; btnSaveConfig = None
tree_programs = None; inpProgPathAdd = None; chkEnabledVar = None; chkEnabledAdd = None
btnAddProg = None; btnRemoveProg = None; btnEditProg = None; btnBrowseAdd = None
btnStartWatchdog = None; btnStopWatchdog = None; btnExitApp = None
status_bar_text = None; style = None; help_font = None

# --- Thread-sichere Debugging/Status Funktion (final V4, fängt TclError früher) ---
def debug_log(message):
    """Gibt Debug-Nachricht aus und aktualisiert Statusleiste Thread-sicher."""
    log_message = f"DEBUG ({time.strftime('%H:%M:%S')}): {message}"
    if DEBUG_MODE:
        print(log_message) # Konsole bleibt wichtig für Debugging

    # Interne Hilfsfunktion zum sicheren Setzen des Status im Hauptthread
    def _update_status_safe(msg_to_set):
        try:
             # Prüfe nur noch, ob die Variablen initialisiert wurden
             if root and status_bar_text:
                 status_bar_text.set(msg_to_set)
        except tk.TclError: pass # Widget zerstört, stillschweigend ignorieren
        except Exception as e_update: print(f"LOG-ERROR: Status Set Error: {e_update}")

    try:
        # Nur versuchen zu aktualisieren, wenn root initialisiert wurde
        if root and status_bar_text:
            # Dieser try/except fängt Fehler bei winfo_exists() ODER root.after() ab
            try:
                if root.winfo_exists(): # Diese Prüfung kann den Fehler werfen
                    current_thread = threading.current_thread()
                    main_thread = threading.main_thread()
                    status_update_msg = message[:120] # Nachricht kürzen

                    if current_thread == main_thread:
                        _update_status_safe(status_update_msg) # Direkter Aufruf
                    else:
                        # Übergabe an den Hauptthread via root.after
                        # root.after kann auch fehlschlagen, wenn root zerstört wird
                        root.after(0, _update_status_safe, status_update_msg)
                # else: Fenster existiert nicht mehr, nichts tun.
            except tk.TclError:
                pass # Ignoriere TclError, der durch Zugriff auf bereits zerstörtes Fenster entsteht
    except Exception as e:
        # Andere allgemeine Fehler in debug_log
        print(f"LOG-ERROR: General debug_log Error: {e}")
        pass # Fehler leise ignorieren

# --- Speichert das aktuelle config Objekt in die INI ---
def save_config_to_file():
    """Schreibt das globale config-Objekt in die INI-Datei."""
    global config; debug_log(f"Schreibe INI: {CONFIG_FILE}")
    try:
        if config.has_section('Settings'):
            if config.has_option('Settings', 'checkcycle'): config.remove_option('Settings', 'checkcycle')
            if config.has_option('Settings', 'startdelay'): config.remove_option('Settings', 'startdelay')
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile: config.write(configfile)
        debug_log("...INI schreiben erfolgreich."); return True
    except Exception as e: debug_log(f"FEHLER Schreiben INI: {e}"); messagebox.showerror("Fehler", f"Fehler Schreiben Konfig:\n{e}", parent=root); return False

# --- Erstellt eine neue INI mit Standardwerten ---
def create_default_ini():
    """Erstellt neues Config-Objekt mit Defaults und speichert es."""
    global config; debug_log("Erstelle Standard-INI Konfig...")
    config = configparser.ConfigParser(inline_comment_prefixes=('#',';'), interpolation=None)
    config.add_section('Settings'); config['Settings']['CheckCycleSec'] = str(DEFAULT_CHECK_CYCLE_SEC); config['Settings']['StartDelaySec'] = str(DEFAULT_START_DELAY_SEC)
    debug_log(f"... Defaults: Cycle={DEFAULT_CHECK_CYCLE_SEC}s, Delay={DEFAULT_START_DELAY_SEC}s")
    saved = save_config_to_file();
    if not saved: debug_log("!!! FEHLER Erstellen Default-INI!")
    return saved

# --- Lädt Settings und Programme ---
def load_settings_and_programs():
    """Lädt Einstellungen und Programmliste aus INI (erstellt ggf. Default-INI)."""
    global config, program_list, check_cycle_sec, start_delay_sec, program_count
    global check_cycle_var_sec, start_delay_var_sec, tree_programs
    debug_log(f"Prüfe/Lese Konfigurationsdatei: {CONFIG_FILE}")
    config = configparser.ConfigParser(inline_comment_prefixes=('#',';'), interpolation=None); program_list = []; program_count = 0
    if tree_programs:
         try: [tree_programs.delete(item) for item in tree_programs.get_children()]
         except Exception as e: debug_log(f"Fehler Leeren Treeview: {e}")
    config_source = "Default"
    if not os.path.exists(CONFIG_FILE):
        debug_log(f"INFO: INI nicht gefunden -> Erstelle Default."); config_created = create_default_ini()
        if not config_created: check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC; start_delay_sec = DEFAULT_START_DELAY_SEC
    else:
        try:
            if not config.read(CONFIG_FILE, encoding='utf-8'): debug_log(f"WARNUNG: INI leer/lesbar?. Verwende Defaults.")
            config_source = "INI-Datei"
        except Exception as e: debug_log(f"FEHLER Lesen INI: {e}. Verwende Defaults.")
    try:
        check_cycle_sec = config.getint('Settings', 'CheckCycleSec', fallback=DEFAULT_CHECK_CYCLE_SEC)
        start_delay_sec = config.getint('Settings', 'StartDelaySec', fallback=DEFAULT_START_DELAY_SEC)
        if check_cycle_sec < 1: check_cycle_sec = 1
        if start_delay_sec < 0: start_delay_sec = 0
    except Exception as e: debug_log(f"FEHLER Verarbeiten [Settings]: {e}. Verwende Defaults."); check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC; start_delay_sec = DEFAULT_START_DELAY_SEC
    debug_log(f"Settings aus '{config_source}' verwendet: Cycle={check_cycle_sec}s, Delay={start_delay_sec}s")
    if check_cycle_var_sec: check_cycle_var_sec.set(str(check_cycle_sec))
    if start_delay_var_sec: start_delay_var_sec.set(str(start_delay_sec))
    debug_log("Lade Programmliste..."); prog_sections = [s for s in config.sections() if s.lower().startswith('program')]
    def get_prog_num(section_name): num_part = section_name[7:]; return int(num_part) if num_part.isdigit() else 9999
    try: prog_sections.sort(key=get_prog_num)
    except ValueError: debug_log("Warnung: Konnte Sektionen nicht sortieren.")
    for section_name in prog_sections:
        try:
            name = config.get(section_name, 'Name', fallback='').strip(); path = config.get(section_name, 'Path', fallback='').strip(); enabled = config.getboolean(section_name, 'Enabled', fallback=False)
            if name and path:
                program_list.append({'name': name, 'path': path, 'enabled': enabled, 'section': section_name}); program_count += 1
                if tree_programs: values = (program_count, name, path, str(enabled)); tree_programs.insert("", tk.END, iid=section_name, values=values, tags=('disabled_row',) if not enabled else ())
            else: debug_log(f"... Sektion '{section_name}' übersprungen.")
        except Exception as e: debug_log(f"FEHLER Lesen Sektion {section_name}: {e}")
    if tree_programs:
        try: tree_programs.tag_configure('disabled_row', foreground='gray')
        except Exception as e: debug_log(f"Fehler Konfig Treeview-Tag: {e}")
    debug_log(f"Programmliste Ladevorgang abgeschlossen. {program_count} Programme.");
    if root and root.winfo_exists(): root.after(50, _update_action_buttons_state)
    return True

# --- Speichert Settings ---
def save_settings_from_gui():
    global check_cycle_sec, start_delay_sec, config; debug_log(">>> Event: Speichern Klick")
    try:
        new_check_cycle_s = int(check_cycle_var_sec.get()); new_start_delay_s = int(start_delay_var_sec.get())
        if new_check_cycle_s < 1: new_check_cycle_s = 1;
        if new_start_delay_s < 0: new_start_delay_s = 0;
        check_cycle_sec = new_check_cycle_s; start_delay_sec = new_start_delay_s
        check_cycle_var_sec.set(str(check_cycle_sec)); start_delay_var_sec.set(str(start_delay_sec))
        debug_log(f"Aktualisiere Settings: CycleSec={check_cycle_sec}, DelaySec={start_delay_sec}")
        if not config.has_section('Settings'): config.add_section('Settings')
        config['Settings']['CheckCycleSec'] = str(check_cycle_sec); config['Settings']['StartDelaySec'] = str(start_delay_sec)
        if save_config_to_file(): messagebox.showinfo("Gespeichert", "Einstellungen gespeichert.", parent=root)
    except ValueError: messagebox.showerror("Fehler", "Ungültige Zahl in Einstellungen.", parent=root)
    except Exception as e: debug_log(f"FEHLER Speichern Settings: {e}"); messagebox.showerror("Fehler", f"Fehler Speichern:\n{e}", parent=root)

# --- Hilfsfunktion Button-Status ---
def _update_action_buttons_state():
    """Aktiviert/Deaktiviert Bearbeiten/Entfernen-Buttons."""
    if not root or not tree_programs or not btnRemoveProg or not btnEditProg: return
    try:
        selected_items = tree_programs.selection()
        if len(selected_items) == 1:
             btnRemoveProg.config(state=tk.NORMAL)
             btnEditProg.config(state=tk.NORMAL)
        else:
             btnRemoveProg.config(state=tk.DISABLED)
             btnEditProg.config(state=tk.DISABLED)
    except tk.TclError: pass # Fenster könnte geschlossen werden
    except Exception as e:
        debug_log(f"Fehler in _update_action_buttons_state: {e}")
        try: # Fehlerbehandlung beim Deaktivieren
            if btnRemoveProg: btnRemoveProg.config(state=tk.DISABLED)
            if btnEditProg: btnEditProg.config(state=tk.DISABLED)
        except Exception: pass

# --- Prozess-Management ---
def is_process_running(process_name):
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'].lower() == process_name.lower(): return True
            except: pass
        return False
    except Exception as e: debug_log(f"FEHLER psutil: {e}"); return False

def start_program(program_path):
    # debug_log(f"Starte: {program_path}")
    if not os.path.exists(program_path): debug_log(f"FEHLER: Pfad nicht existent: {program_path}"); return False
    try: program_dir = os.path.dirname(program_path); creationflags = subprocess.CREATE_NO_WINDOW if IS_BUNDLED and sys.platform == "win32" else 0; subprocess.Popen([program_path], cwd=program_dir, creationflags=creationflags); return True
    except Exception as e: debug_log(f"FEHLER Starten von {program_path}: {e}"); return False

# --- Watchdog Hauptschleife ---
STATE_WAIT_CHECK = 0; STATE_CHECKING = 1; STATE_WAIT_DELAY = 2
def watchdog_loop(stop_event_thread):
    global watchdog_state, last_check_completion_time, last_program_start_time, current_program_index
    local_program_list_copy = program_list[:]; local_check_cycle_sec = float(check_cycle_sec); local_start_delay_sec = float(start_delay_sec)
    if not local_program_list_copy: debug_log("Watchdog-Thread: Keine Programme."); root.after(0, update_watchdog_buttons_on_stop); return
    debug_log(f"Watchdog-Thread gestartet. Zyklus: {local_check_cycle_sec:.1f}s, Delay: {local_start_delay_sec:.1f}s")
    watchdog_state = STATE_CHECKING; current_program_index = 0; last_check_completion_time = 0.0; last_program_start_time = 0.0
    while not stop_event_thread.is_set():
        now = time.monotonic(); process_next_state_immediately = False
        # --- Verwende die Kopie der Liste für einen Zyklus ---
        current_list_len = len(local_program_list_copy)

        if watchdog_state == STATE_WAIT_CHECK:
            if last_check_completion_time == 0.0: last_check_completion_time = now
            if (now - last_check_completion_time) >= local_check_cycle_sec:
                local_program_list_copy = program_list[:] # Liste für den neuen Zyklus holen
                current_list_len = len(local_program_list_copy) # Länge aktualisieren
                if current_list_len > 0: debug_log("Watchdog: Zyklus beginnt..."); current_program_index = 0; watchdog_state = STATE_CHECKING; process_next_state_immediately = True
                else: debug_log("Watchdog: Zyklus, keine Programme."); last_check_completion_time = now
        elif watchdog_state == STATE_CHECKING:
            process_next_state_immediately = True
            if current_program_index >= current_list_len: debug_log("Watchdog: Zyklus abgeschlossen."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
            else:
                program = local_program_list_copy[current_program_index]
                if not program['enabled']: current_program_index += 1
                elif is_process_running(program['name']): current_program_index += 1
                else:
                    debug_log(f"Watchdog: Prozess '{program['name']}' läuft nicht -> Starte...")
                    if start_program(program['path']): debug_log(f"... Warte {local_start_delay_sec:.1f}s."); last_program_start_time = now; watchdog_state = STATE_WAIT_DELAY; process_next_state_immediately = False
                    else: debug_log(f"... FEHLER Start '{program['name']}'."); current_program_index += 1
                if current_program_index >= current_list_len and watchdog_state == STATE_CHECKING: debug_log("Watchdog: Zyklus beendet (nach Check/Skip)."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
        elif watchdog_state == STATE_WAIT_DELAY:
            process_next_state_immediately = True
            elapsed_since_start = now - last_program_start_time
            if elapsed_since_start >= local_start_delay_sec:
                 if current_program_index < current_list_len: program_name = local_program_list_copy[current_program_index]['name']
                 else: program_name = "?"; debug_log("WARNUNG: Index out of bounds in WAIT_DELAY")
                 debug_log(f"Watchdog: Startverzögerung '{program_name}' beendet."); current_program_index += 1; watchdog_state = STATE_CHECKING
                 if current_program_index >= current_list_len: debug_log("Watchdog: Zyklus beendet (nach letztem Delay)."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
            else: process_next_state_immediately = False
        # --- Sleep Logic ---
        if not process_next_state_immediately:
            wait_time = SHORT_ADLIB_INTERVAL_SEC;
            if watchdog_state == STATE_WAIT_CHECK: time_to_next_check = max(0, local_check_cycle_sec - (now - last_check_completion_time)); wait_time = min(wait_time, time_to_next_check) if last_check_completion_time > 0 else wait_time
            elif watchdog_state == STATE_WAIT_DELAY: time_to_delay_end = max(0, local_start_delay_sec - (now - last_program_start_time)); wait_time = min(wait_time, time_to_delay_end)
            wait_time = max(0.1, wait_time); stopped = stop_event_thread.wait(timeout=wait_time)
            if stopped: break
        elif stop_event_thread.is_set(): break
    debug_log("Watchdog-Thread: Schleife beendet.");
    if root and root.winfo_exists(): root.after(0, update_watchdog_buttons) # Korrigierter Funktionsname

# --- GUI Erstellung ---
def create_gui_widgets():
    """Erstellt die Widgets im Hauptfenster 'root'."""
    global root, check_cycle_var_sec, start_delay_var_sec, btnSaveConfig, tree_programs
    global inpProgPathAdd, chkEnabledVar, chkEnabledAdd, btnBrowseAdd, btnAddProg, btnRemoveProg
    global btnEditProg, btnStartWatchdog, btnStopWatchdog, btnExitApp, status_bar_text, style, help_font
    root.title("Watchdog"); root.geometry("550x500")
    try: help_font = tkFont.Font(family=ttk.Style().lookup('TLabel', 'font'), size=8)
    except Exception as e: debug_log(f"Fehler Font: {e}"); help_font = None
    check_cycle_var_sec = tk.StringVar(root); start_delay_var_sec = tk.StringVar(root)
    chkEnabledVar = tk.BooleanVar(root, value=True); status_bar_text = tk.StringVar(root, value="Bereit.")
    # Settings Frame
    settings_frame = ttk.LabelFrame(root, text="Einstellungen", padding="10"); settings_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew"); settings_frame.columnconfigure(3, weight=1)
    ttk.Label(settings_frame, text="Prüfzyklus (s):").grid(row=0, column=0, padx=(5,0), pady=5, sticky="w"); cycle_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", foreground="blue", font=help_font); cycle_help.grid(row=0, column=1, padx=(0,5), pady=5, sticky="w"); cycle_help.bind("<Button-1>", lambda e: show_help_cycle())
    cycle_entry = ttk.Entry(settings_frame, textvariable=check_cycle_var_sec, width=8); cycle_entry.grid(row=0, column=2, padx=5, pady=5, sticky="w")
    ttk.Label(settings_frame, text="Startverzögerung (s):").grid(row=1, column=0, padx=(5,0), pady=5, sticky="w"); delay_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", foreground="blue", font=help_font); delay_help.grid(row=1, column=1, padx=(0,5), pady=5, sticky="w"); delay_help.bind("<Button-1>", lambda e: show_help_delay())
    delay_entry = ttk.Entry(settings_frame, textvariable=start_delay_var_sec, width=8); delay_entry.grid(row=1, column=2, padx=5, pady=5, sticky="w")
    btnSaveConfig = ttk.Button(settings_frame, text="Settings speichern", command=save_settings_from_gui); btnSaveConfig.grid(row=0, column=4, rowspan=2, padx=20, pady=5, sticky="e")
    # Program List Frame
    programs_frame = ttk.LabelFrame(root, text="Programme", padding="10"); programs_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
    programs_frame.columnconfigure(0, weight=1); programs_frame.rowconfigure(0, weight=1)
    columns = ("nr", "name", "path", "enabled"); tree_programs = ttk.Treeview(programs_frame, columns=columns, show='headings', selectmode='browse')
    tree_programs.heading("nr", text="Nr."); tree_programs.heading("name", text="Name (aus Pfad)"); tree_programs.heading("path", text="Pfad"); tree_programs.heading("enabled", text="Aktiviert")
    tree_programs.column("nr", width=30, stretch=tk.NO, anchor='e'); tree_programs.column("name", width=120); tree_programs.column("path", width=250); tree_programs.column("enabled", width=60, anchor='center')
    scrollbar = ttk.Scrollbar(programs_frame, orient=tk.VERTICAL, command=tree_programs.yview); tree_programs.configure(yscroll=scrollbar.set)
    tree_programs.grid(row=0, column=0, sticky='nsew'); scrollbar.grid(row=0, column=1, sticky='ns')
    tree_programs.bind('<<TreeviewSelect>>', on_list_selection_change); tree_programs.bind('<Double-1>', on_edit_button_click)
    # Add Frame
    add_frame = ttk.LabelFrame(root, text="Programm hinzufügen", padding="10"); add_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew"); add_frame.columnconfigure(2, weight=1)
    ttk.Label(add_frame, text="Pfad:").grid(row=0, column=0, padx=(5,0), pady=2, sticky="w"); path_add_help = ttk.Label(add_frame, text="(?)", cursor="question_arrow", foreground="blue", font=help_font); path_add_help.grid(row=0, column=1, padx=(0,5), pady=2, sticky="w"); path_add_help.bind("<Button-1>", lambda e: show_help_path_add())
    inpProgPathAdd = ttk.Entry(add_frame, width=50); inpProgPathAdd.grid(row=0, column=2, padx=5, pady=2, sticky="ew"); btnBrowseAdd = ttk.Button(add_frame, text="...", width=3, command=on_browse_button_click); btnBrowseAdd.grid(row=0, column=3, padx=5, pady=2)
    chkEnabledAdd = ttk.Checkbutton(add_frame, text="Aktiviert", variable=chkEnabledVar); chkEnabledAdd.grid(row=1, column=2, padx=5, pady=5, sticky="w"); btnAddProg = ttk.Button(add_frame, text="Hinzufügen", command=on_add_button_click); btnAddProg.grid(row=1, column=3, padx=5, pady=5, sticky="e")
    # Bottom Frame
    bottom_frame = ttk.Frame(root, padding="10"); bottom_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew"); bottom_frame.columnconfigure(1, weight=1) # Spacer Spalte 1
    edit_remove_frame = ttk.Frame(bottom_frame); edit_remove_frame.grid(row=0, column=0, sticky="w")
    btnEditProg = ttk.Button(edit_remove_frame, text="Bearbeiten", command=on_edit_button_click, state=tk.DISABLED); btnEditProg.pack(side=tk.TOP, anchor="w", pady=(0, 2))
    btnRemoveProg = ttk.Button(edit_remove_frame, text="Entfernen", command=on_remove_button_click, state=tk.DISABLED); btnRemoveProg.pack(side=tk.TOP, anchor="w")
    start_stop_frame = ttk.Frame(bottom_frame); start_stop_frame.grid(row=0, column=2, sticky="ns")
    btnStartWatchdog = ttk.Button(start_stop_frame, text="Start", command=on_start_watchdog_click); btnStartWatchdog.pack(side=tk.TOP, anchor="center", pady=(0, 2))
    btnStopWatchdog = ttk.Button(start_stop_frame, text="Stop", command=on_stop_watchdog_click, state=tk.DISABLED); btnStopWatchdog.pack(side=tk.TOP, anchor="center")
    btnExitApp = ttk.Button(bottom_frame, text="Beenden", command=on_exit_button_click); btnExitApp.grid(row=0, column=3, padx=(20, 5), pady=5, sticky="e")
    # Status Bar
    status_bar = ttk.Label(root, textvariable=status_bar_text, relief=tk.SUNKEN, anchor=tk.W, padding="2 5"); status_bar.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 5))
    # Grid Config Root
    root.columnconfigure(0, weight=1); root.rowconfigure(1, weight=1)
    root.protocol("WM_DELETE_WINDOW", on_exit_button_click)

# --- Hilfe-Funktionen ---
def show_help_cycle(): messagebox.showinfo("Hilfe: Prüfzyklus", "Zeit in Sekunden (s), nach der geprüft wird.", parent=root)
def show_help_delay(): messagebox.showinfo("Hilfe: Startverzögerung", "Zeit in Sekunden (s), die nach Start gewartet wird, bevor nächstes Programm geprüft/gestartet wird.", parent=root)
def show_help_path_add(): messagebox.showinfo("Hilfe: Pfad", "Pfad zur .exe Datei.\nProzessname wird daraus extrahiert.", parent=root)

# --- Event Handler ---
def on_list_selection_change(event=None): root.after(50, _update_action_buttons_state)
def on_browse_button_click():
    debug_log(">>> Event: Browse Add Path Click"); sFilePath = filedialog.askopenfilename( title="Programm auswählen", initialdir=os.path.dirname(inpProgPathAdd.get()) if inpProgPathAdd.get() else application_path, filetypes=[("Ausführbare Dateien", "*.exe"), ("Alle Dateien", "*.*")], parent=root ); root.focus_force()
    if sFilePath: normalized_path = os.path.normpath(sFilePath); debug_log(f"Ausgewählt: {normalized_path}"); inpProgPathAdd.delete(0, tk.END); inpProgPathAdd.insert(0, normalized_path)
    else: debug_log("Keine Datei ausgewählt.")
def on_add_button_click():
    debug_log(">>> Event: OnAddButtonClick"); new_path = inpProgPathAdd.get().strip(); new_enabled = chkEnabledVar.get(); debug_log(f"Add: Path='{new_path}', Enabled={new_enabled}")
    if not new_path: messagebox.showwarning("Eingabe fehlt", "Pfad leer.", parent=root); return
    monitor_name = os.path.basename(new_path);
    if not monitor_name: messagebox.showerror("Fehler", "Kein Dateiname extrahierbar.", parent=root); return
    if not monitor_name.lower().endswith(".exe"):
        if not messagebox.askyesno("Warnung", f"'{monitor_name}' keine .exe?\nTrotzdem?", parent=root): return
    for prog in program_list:
        if prog['name'].lower() == monitor_name.lower(): messagebox.showwarning("Doppelt", f"'{monitor_name}' existiert.", parent=root); return
    i = 1;
    while True: # Korrigiert
        section_name = f"Program{i}"
        if not config.has_section(section_name): break
        i += 1
        if i > 999: messagebox.showerror("Fehler", "Limit 999."); return
    debug_log(f"Füge als Sektion hinzu: {section_name}")
    try:
        if not config.has_section(section_name): config.add_section(section_name)
        config.set(section_name, 'Name', monitor_name); config.set(section_name, 'Path', new_path); config.set(section_name, 'Enabled', str(new_enabled))
        if save_config_to_file(): debug_log("INI geschrieben (Add)."); load_settings_and_programs(); inpProgPathAdd.delete(0, tk.END); chkEnabledVar.set(True); messagebox.showinfo("Erfolg", f"'{monitor_name}' hinzugefügt.", parent=root)
    except Exception as e: debug_log(f"FEHLER Add/Save: {e}"); messagebox.showerror("Fehler", f"Fehler Hinzufügen:\n{e}", parent=root)
def on_remove_button_click():
    debug_log(">>> Event: OnRemoveButtonClick"); selected_items = tree_programs.selection();
    if not selected_items: messagebox.showwarning("Keine Auswahl", "Programm auswählen.", parent=root); return
    selected_iid = selected_items[0]; debug_log(f"Entferne: {selected_iid}")
    try:
        prog_name_to_remove = config.get(selected_iid, 'Name', fallback=selected_iid)
        if not messagebox.askyesno("Bestätigung", f"Soll '{prog_name_to_remove}' entfernt werden?", parent=root): debug_log("Entfernen abgebrochen."); return
        removed = config.remove_section(selected_iid)
        if not removed: debug_log(f"Sektion {selected_iid} nicht entfernt."); messagebox.showerror("Fehler", f"Konnte Sektion nicht entfernen.", parent=root); return
        if save_config_to_file(): debug_log("INI geschrieben (Remove)."); load_settings_and_programs(); messagebox.showinfo("Erfolg", f"'{prog_name_to_remove}' entfernt.", parent=root)
    except Exception as e: debug_log(f"FEHLER Remove/Save: {e}"); messagebox.showerror("Fehler", f"Fehler Entfernen:\n{e}", parent=root)
def on_edit_button_click(event=None):
    debug_log(">>> Event: OnEditButtonClick"); selected_items = tree_programs.selection()
    if not selected_items or len(selected_items) > 1:
        if event:
            focused_item = tree_programs.focus()
            if focused_item:
                selected_items = (focused_item,)
                tree_programs.selection_set(focused_item)
            else: messagebox.showwarning("Auswahlfehler", "Programm auswählen.", parent=root); return
        else: messagebox.showwarning("Auswahlfehler", "Programm auswählen.", parent=root); return
    selected_iid = selected_items[0]; debug_log(f"Bearbeite: {selected_iid}")
    try:
        current_name = config.get(selected_iid, 'Name', fallback=""); current_path = config.get(selected_iid, 'Path', fallback=""); current_enabled = config.getboolean(selected_iid, 'Enabled', fallback=False)
        edit_window = tk.Toplevel(root); edit_window.title(f"Bearbeite: {current_name}"); edit_window.resizable(False, False); edit_window.transient(root); edit_window.grab_set()
        path_var_edit = tk.StringVar(edit_window, value=current_path); enabled_var_edit = tk.BooleanVar(edit_window, value=current_enabled)
        dialog_frame = ttk.Frame(edit_window, padding="10"); dialog_frame.pack(expand=True, fill=tk.BOTH); dialog_frame.columnconfigure(1, weight=1)
        ttk.Label(dialog_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w"); name_display_label = ttk.Label(dialog_frame, text=current_name, width=40, relief=tk.SUNKEN, anchor="w"); name_display_label.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        ttk.Label(dialog_frame, text="Pfad:").grid(row=1, column=0, padx=5, pady=5, sticky="w"); path_entry = ttk.Entry(dialog_frame, textvariable=path_var_edit, width=40); path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        def _browse_edit_path():
            edit_window.grab_release(); sFilePath = filedialog.askopenfilename( title="Programm auswählen", initialdir=os.path.dirname(path_var_edit.get()) if path_var_edit.get() else application_path, filetypes=[("Ausführbare Dateien", "*.exe"), ("Alle Dateien", "*.*")], parent=edit_window ); edit_window.grab_set(); edit_window.focus_force()
            if sFilePath: path_var_edit.set(os.path.normpath(sFilePath))
        browse_button_edit = ttk.Button(dialog_frame, text="...", width=3, command=_browse_edit_path); browse_button_edit.grid(row=1, column=2, padx=5, pady=5)
        enabled_check_edit = ttk.Checkbutton(dialog_frame, text="Aktiviert", variable=enabled_var_edit); enabled_check_edit.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="w")
        button_frame = ttk.Frame(dialog_frame); button_frame.grid(row=3, column=0, columnspan=3, pady=10)
        def _save_edit_and_close():
            new_path = path_var_edit.get().strip(); new_enabled = enabled_var_edit.get()
            if not new_path: messagebox.showerror("Fehler", "Pfad leer.", parent=edit_window); return
            new_monitor_name = os.path.basename(new_path)
            if not new_monitor_name: messagebox.showerror("Fehler", "Kein Dateiname extrahierbar.", parent=edit_window); return
            if not new_monitor_name.lower().endswith(".exe"):
                 if not messagebox.askyesno("Warnung", f"'{new_monitor_name}' keine .exe?\nSpeichern?", parent=edit_window): return
            if new_monitor_name.lower() != current_name.lower(): # Nur prüfen, wenn Name sich ÄNDERT
                for prog in program_list:
                    if prog['section'] != selected_iid and prog['name'].lower() == new_monitor_name.lower(): messagebox.showerror("Fehler", f"Anderes Prog namens '{new_monitor_name}' existiert.", parent=edit_window); return
            try:
                config.set(selected_iid, 'Name', new_monitor_name); config.set(selected_iid, 'Path', new_path); config.set(selected_iid, 'Enabled', str(new_enabled))
                if save_config_to_file(): debug_log(f"INI nach Edit von {selected_iid} gespeichert."); load_settings_and_programs(); edit_window.destroy()
            except Exception as e: debug_log(f"FEHLER Speichern nach Edit: {e}"); messagebox.showerror("Fehler", f"Fehler Speichern:\n{e}", parent=edit_window)
        ok_button = ttk.Button(button_frame, text="OK", command=_save_edit_and_close); ok_button.pack(side=tk.LEFT, padx=10)
        cancel_button = ttk.Button(button_frame, text="Abbrechen", command=edit_window.destroy); cancel_button.pack(side=tk.LEFT, padx=10)
        path_entry.focus_set(); edit_window.wait_window()
    except Exception as e: debug_log(f"FEHLER Öffnen Edit-Dialog: {e}"); messagebox.showerror("Fehler", f"Fehler Öffnen Edit-Dialog:\n{e}", parent=root)
    debug_log("<<< Event: OnEditButtonClick Ende.")
def on_start_watchdog_click():
    global is_running, watchdog_thread, stop_event; debug_log(">>> Event: OnStartWatchdogClick")
    if not is_running:
        load_settings_and_programs();
        if not program_list: messagebox.showwarning("Keine Programme", "Keine Programme konfiguriert.", parent=root); return
        is_running = True; stop_event = threading.Event(); debug_log("Erstelle/starte Watchdog-Thread...")
        watchdog_thread = threading.Thread(target=watchdog_loop, args=(stop_event,), daemon=True)
        watchdog_thread.start()
        update_watchdog_buttons(); status_bar_text.set("Watchdog läuft...") ; debug_log("Watchdog Gestartet.")
    else: debug_log("Watchdog lief bereits.")
def on_stop_watchdog_click():
    global is_running; debug_log(">>> Event: OnStopWatchdogClick")
    if is_running:
        debug_log("Sende Stop-Signal...")
        if stop_event:
             stop_event.set()
        is_running = False; update_watchdog_buttons(); status_bar_text.set("Watchdog stoppt...")
        if root: root.after(100, _check_thread_stopped)
    else: debug_log("Watchdog war bereits gestoppt.")
def _check_thread_stopped():
    global is_running, watchdog_thread;
    if watchdog_thread and watchdog_thread.is_alive(): debug_log("Thread läuft noch, warte..."); root.after(500, _check_thread_stopped)
    else:
        if not is_running and status_bar_text and status_bar_text.get() == "Watchdog stoppt...": debug_log("Thread beendet (Stop)."); watchdog_thread = None; status_bar_text.set("Watchdog gestoppt."); debug_log("Watchdog Gestoppt (Inaktiv)."); update_watchdog_buttons()
def update_watchdog_buttons_on_stop():
    global is_running, watchdog_thread; debug_log("Thread hat sich selbst beendet.");
    if is_running: is_running = False; watchdog_thread = None; update_watchdog_buttons(); status_bar_text.set("Watchdog beendet.")
def update_watchdog_buttons():
     if not root or not btnStartWatchdog or not btnStopWatchdog: return
     try:
         start_state = tk.NORMAL if not is_running else tk.DISABLED
         stop_state = tk.NORMAL if is_running else tk.DISABLED
         if btnStartWatchdog:
             btnStartWatchdog.config(state=start_state)
         if btnStopWatchdog:
             btnStopWatchdog.config(state=stop_state)
     except Exception as e: debug_log(f"Fehler Update Watchdog-Buttons: {e}")
def on_exit_button_click():
     debug_log(">>> Event: Exit Button Click / Window Close")
     if is_running:
         debug_log("Stoppe Watchdog vor Beenden...")
         if stop_event:
             stop_event.set()
         if watchdog_thread:
             watchdog_thread.join(timeout=SHORT_ADLIB_INTERVAL_SEC + 0.5)
             if watchdog_thread.is_alive():
                 debug_log("WARNUNG: Watchdog-Thread nicht rechtzeitig beendet.")
     if root:
        try:
             debug_log("Zerstöre Hauptfenster...")
             root.destroy()
        except Exception as e:
             debug_log(f"Fehler Zerstören Fenster: {e}")
def WM_CLOSE_HANDLER(): on_exit_button_click()

# --- Hauptteil ---
if __name__ == "__main__":
    debug_log("Watchdog Skript Start (GUI Modus)")
    root = None; style = None
    try:
        root = tk.Tk(); root.withdraw()
        # === NEU: Fenster-Icon setzen (mit resource_path) ===
        try:
            icon_filename = "watchdog.ico"
            # Verwende resource_path, um den Pfad zur (ggf. eingebetteten) Datei zu finden
            icon_path = resource_path(icon_filename)
            debug_log(f"Versuche Icon zu laden von: {icon_path}") # Logge den Pfad
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
                debug_log("Fenster-Icon gesetzt.")
            else:
                debug_log(f"WARNUNG: Icon-Datei nicht gefunden unter (via resource_path): {icon_path}")
        except tk.TclError as icon_error:
            debug_log(f"FEHLER beim Setzen des Fenster-Icons: {icon_error}")
        except Exception as e:
            debug_log(f"Allgemeiner Fehler beim Icon-Setzen: {e}")
        # === ENDE NEU ===
        try: style = ttk.Style();
        except Exception as e: debug_log(f"Style Init Fehler: {e}")
        create_gui_widgets(); load_settings_and_programs(); update_watchdog_buttons()
        root.deiconify()
        debug_log("Starte Watchdog automatisch beim Start...")
        root.after(100, on_start_watchdog_click) # << AUTO-START
        root.mainloop()
    except Exception as e:
        debug_log(f"Kritischer Fehler GUI-Start: {e}")
        # Korrigierter Except-Block
        if root and root.winfo_exists():
             try:
                 debug_log("Versuche, root-Fenster zu zerstören...")
                 root.destroy()
             except Exception as e_destroy:
                 debug_log(f"Fehler Zerstören Fenster im Fehlerfall: {e_destroy}"); pass
        try: import traceback; tk_error = tk.Tk(); tk_error.withdraw(); messagebox.showerror("Schwerwiegender Fehler", f"Anwendung nicht gestartet:\n\n{traceback.format_exc()}", parent=None); tk_error.destroy()
        except Exception as e2: print(f"Kritischer Fehler, MsgBox Fehler: {e}\nZusätzlicher Fehler: {e2}"); print(traceback.format_exc())
    finally:
        debug_log("Finale Aufräumarbeiten...");
        if is_running and stop_event:
            debug_log("Stoppe verbl. Watchdog-Thread...");
            stop_event.set()
            if watchdog_thread:
                 watchdog_thread.join(timeout=1.0)
        debug_log("Watchdog Skript Ende")
        