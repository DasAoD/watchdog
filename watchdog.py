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
import json
try:
    import winreg
    CAN_CHECK_REGISTRY = True
except ImportError:
    CAN_CHECK_REGISTRY = False
    print("WARNUNG: Modul 'winreg' nicht gefunden. System-Theme-Erkennung nicht verfügbar.")
import sv_ttk # Für Dark/Light Theme

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
    application_path = os.getcwd(); CONFIG_FILE = os.path.join(application_path, 'watchdog.ini'); IS_BUNDLED = False

DEFAULT_CHECK_CYCLE_SEC = 60
DEFAULT_START_DELAY_SEC = 15
DEBUG_MODE = False
SHORT_ADLIB_INTERVAL_SEC = 1.0
BASE_FONT_SIZE = 10 # NEU: Globale Basisschriftgröße (z.B. 8, 9, 10)

# Globale Variablen
config = configparser.ConfigParser(inline_comment_prefixes=('#',';'), interpolation=None)
program_list = []
check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC
start_delay_sec = DEFAULT_START_DELAY_SEC
program_count = 0
is_running = False
watchdog_thread = None
stop_event = None

# i18n Variablen
current_language = "de" # Default
translations = {}
supported_languages = {"Deutsch": "de", "English": "en", "Česky": "cz", "Français": "fr", "Italiano": "it", "Español": "es", "Magyar": "hu"}
language_var = None

# Theme Variablen
theme_preference_var = None
current_theme_setting = "system"

# Watchdog State Machine Variablen
watchdog_state = 0; last_check_completion_time = 0.0; last_program_start_time = 0.0; current_program_index = 0

# GUI Elemente Handles
root = None; check_cycle_var_sec = None; start_delay_var_sec = None; btnSaveConfig = None
tree_programs = None; inpProgPathAdd = None; chkEnabledVar = None; chkEnabledAdd = None
btnAddProg = None; btnRemoveProg = None; btnEditProg = None; btnBrowseAdd = None
btnStartWatchdog = None; btnStopWatchdog = None; btnExitApp = None
status_bar_text = None; style = None; help_font = None
lblCheckCycle = None; lblStartDelay = None; lblLanguage = None; lblPathAdd = None; lblTheme = None
settings_frame = None; programs_frame = None; add_frame = None; theme_frame = None
r_system = None; r_light = None; r_dark = None; language_combo = None

# --- Hilfsfunktionen ---
# --- Hilfsfunktionen ---

def get_base_path():
    """Ermittelt den Basispfad für Ressourcen, abhängig davon, ob die Anwendung gebündelt ist."""
    try:
        # PyInstaller erstellt einen temporären Ordner und speichert den Pfad in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Wenn nicht gebündelt, ist der Basispfad der Ordner des Hauptskripts
        base_path = application_path # 'application_path' wird am Anfang des Skripts definiert
    return base_path

def get_lang_resource_path(relative_filename):
    """Gibt den Pfad zu einer Ressource im 'lang'-Unterordner zurück."""
    base_path = get_base_path()
    return os.path.join(base_path, "lang", relative_filename)

def get_icon_resource_path(relative_filename):
    """Gibt den Pfad zu einer Ressource im 'icon'-Unterordner zurück."""
    base_path = get_base_path()
    return os.path.join(base_path, "icon", relative_filename)

# Die alte resource_path Funktion wird nicht mehr direkt verwendet oder kann entfernt werden,
# wenn alle Aufrufe auf die neuen Funktionen umgestellt sind.
# def resource_path(relative_path):
#     try: base_path = sys._MEIPASS
#     except Exception: base_path = application_path
#     return os.path.join(base_path, "lang", relative_path) # Diese war spezifisch für "lang"

def debug_log(message):
    log_message = f"DEBUG ({time.strftime('%H:%M:%S')}): {message}"
    if DEBUG_MODE: print(log_message)
    def _update_status_safe(msg_to_set):
        try:
             if root and root.winfo_exists() and status_bar_text: status_bar_text.set(msg_to_set)
        except tk.TclError: pass
        except Exception as e_update: print(f"LOG-ERROR: Status Set Error: {e_update}")
    try:
        if root and status_bar_text:
            if root.winfo_exists():
                current_thread = threading.current_thread(); main_thread = threading.main_thread()
                status_update_msg = message[:120]
                if current_thread == main_thread: _update_status_safe(status_update_msg)
                else: root.after(0, _update_status_safe, status_update_msg)
    except tk.TclError: pass
    except Exception as e: print(f"LOG-ERROR: General debug_log Error: {e}"); pass

def apply_custom_font_sizes(base_size):
    global style 

    if not style:
        debug_log("WARNUNG: apply_custom_font_sizes: ttk.Style Objekt nicht initialisiert.")
        return

    try:
        current_font_family = "Calibri" 
        if sys.platform == "darwin": current_font_family = "Helvetica Neue"
        elif sys.platform.startswith("linux"): current_font_family = "DejaVu Sans"
        
        debug_log(f"apply_custom_font_sizes: Verwende Schriftfamilie '{current_font_family}' für Styles. Basisschriftgröße: {base_size}px.")

        base_font_spec = (current_font_family, base_size)

        # 1. Treeview-Überschriften
        treeview_heading_font_spec = (current_font_family, base_size) 
        try:
            style.configure("Treeview.Heading", font=treeview_heading_font_spec)
            debug_log(f"Treeview.Heading style konfiguriert mit Font: {treeview_heading_font_spec}")
        except Exception as e_tv_head:
            debug_log(f"Fehler bei Konfiguration des Treeview.Heading Styles: {e_tv_head}")
        
        # 2. Benutzerdefinierter Style für die "(?)" Hilfe-Labels
        try: 
            help_label_font_obj = tkFont.Font(family=current_font_family, size=max(7, base_size - 1))
            style.configure("Help.TLabel", font=help_label_font_obj, foreground="blue")
            debug_log(f"Help.TLabel style konfiguriert mit Font: {help_label_font_obj.actual()}")
        except Exception as e_help_style: 
            debug_log(f"Fehler beim Konfigurieren des Help.TLabel Styles: {e_help_style}")

        # 3. Schrift für TButton (war schon erfolgreich)
        try:
            style.configure("TButton", font=base_font_spec)
            debug_log(f"TButton style konfiguriert mit Font: {base_font_spec}")
        except Exception as e_button_style:
            debug_log(f"Fehler bei TButton Style Konfiguration: {e_button_style}")

        # 4. Schrift für TRadiobutton (war schon erfolgreich)
        try:
            style.configure("TRadiobutton", font=base_font_spec) 
            debug_log(f"TRadiobutton style konfiguriert mit Font: {base_font_spec}")
        except Exception as e_radio_style:
            debug_log(f"Fehler bei TRadiobutton Style Konfiguration: {e_radio_style}")
            
        # ***** NEU: Schrift für TCheckbutton explizit setzen *****
        try:
            style.configure("TCheckbutton", font=base_font_spec) # Beeinflusst den Text neben der Checkbox
            debug_log(f"TCheckbutton style konfiguriert mit Font: {base_font_spec}")
        except Exception as e_check_style:
            debug_log(f"Fehler bei TCheckbutton Style Konfiguration: {e_check_style}")
        # *********************************************************

        debug_log(f"apply_custom_font_sizes (mit Button/Radio/Checkbutton Anpassung) erfolgreich durchlaufen.")

    except Exception as e: 
        debug_log(f"Allgemeiner FEHLER in apply_custom_font_sizes: {e}")
        import traceback
        traceback.print_exc()

# --- Internationalization (i18n) ---
def load_language(lang_code='de', is_initial_load=False):
    global translations, current_language
    original_requested_lang = lang_code
    # Fallback-Reihenfolge: angeforderte Sprache, dann Englisch, dann Deutsch
    fallback_order = [lang_code, 'en', 'de']
    # Sicherstellen, dass jeder Code nur einmal vorkommt, Reihenfolge beibehalten
    seen = set()
    unique_fallback_order = [x for x in fallback_order if not (x in seen or seen.add(x))]

    loaded_successfully = False
    loaded_lang_code = None # Die Sprache, die tatsächlich geladen wurde

    for code_to_try in unique_fallback_order:
        # lang_file = resource_path(f"{code_to_try}.json") # ALTE ZEILE
        lang_file = get_lang_resource_path(f"{code_to_try}.json") # NEUE ZEILE
        debug_log(f"Versuche Sprachdatei zu laden: '{lang_file}' (für ursprünglich angefordertes '{original_requested_lang}')")

        if not os.path.exists(lang_file):
            debug_log(f"WARNUNG: Sprachdatei '{lang_file}' existiert nicht.")
            continue
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                translations = json.load(f)
            current_language = code_to_try # Globale Variable setzen
            loaded_lang_code = code_to_try
            debug_log(f"Sprachdatei '{lang_file}' erfolgreich geladen und als '{current_language}' gesetzt.")
            loaded_successfully = True
            break  # Schleife bei erfolgreichem Laden verlassen
        except json.JSONDecodeError as e_json:
            debug_log(f"FEHLER: Sprachdatei '{lang_file}' ist fehlerhaft (JSONDecodeError): {e_json}")
            # translations = {} # Optional: Bei Fehler leeren, um partielle Daten zu vermeiden
        except Exception as e:
            debug_log(f"FEHLER beim Laden/Verarbeiten der Sprachdatei '{lang_file}': {e}")
            # translations = {}

    if not loaded_successfully:
        debug_log(f"WARNUNG: Keine Sprachdatei konnte für '{original_requested_lang}' oder definierte Fallbacks geladen werden. Setze auf 'de' (hartkodiert) und versuche, 'de.json' zu laden.")
        translations = {}  # Sicherstellen, dass Übersetzungen leer sind
        current_language = 'de' # Als letzten Ausweg auf Deutsch setzen
        loaded_lang_code = 'de' # Anzeigen, dass Deutsch der aktive Code ist

        # Ein letzter Versuch, die deutsche Sprachdatei zu laden, wenn alles andere fehlschlug
        de_lang_file = resource_path("de.json")
        if os.path.exists(de_lang_file):
            try:
                with open(de_lang_file, 'r', encoding='utf-8') as f_de:
                    translations = json.load(f_de)
                debug_log("Fallback auf hartkodiertes 'de.json' erfolgreich geladen.")
                # current_language ist bereits 'de'
            except Exception as e_de_final:
                debug_log(f"FEHLER: Konnte selbst das hartkodierte 'de.json' nicht laden: {e_de_final}")
                translations = {} # Übersetzungen bleiben definitiv leer
        else:
            debug_log("WARNUNG: Hartkodierte Fallback-Sprachdatei 'de.json' existiert nicht. Übersetzungen bleiben leer.")

    # Benutzerfeedback nur geben, wenn es keine Erstladung ist und relevant
    if not is_initial_load:
        if loaded_successfully and loaded_lang_code != original_requested_lang:
            # Versuche, die Warnmeldung mit den aktuell geladenen Übersetzungen anzuzeigen
            # (kann den Schlüssel selbst anzeigen, wenn die Übersetzung für die Warnung fehlt)
            if root and root.winfo_exists(): # Nur wenn GUI existiert
                 messagebox.showwarning(
                    translate("Language load warning"),
                    translate("The selected language '{}' could not be loaded. Switched to '{}'.").format(original_requested_lang, loaded_lang_code),
                    parent=root
                )
        elif not loaded_successfully and original_requested_lang != 'de': # Wenn auch der Fallback auf 'de' nicht ging (ausser de war eh angefragt)
             if root and root.winfo_exists():
                messagebox.showerror(
                    translate("Language load error"),
                    translate("Neither the selected language '{}' nor any fallback languages could be loaded. Defaulting to basic UI text.").format(original_requested_lang),
                    parent=root
                )
    return loaded_successfully

def translate(key, *args):
    # load_language ist nun allein für das Laden der Übersetzungen zuständig.
    # Wenn translations hier leer ist, bedeutet das, dass alle Ladeversuche (inkl. Fallbacks) gescheitert sind.
    translated = translations.get(key, key) # Fällt auf den Schlüssel selbst zurück, wenn nicht gefunden
    try:
        return translated.format(*args) if args else translated
    except KeyError: # Tritt auf, wenn der Schlüssel Formatierungsplatzhalter hat, aber nicht in translations gefunden wird
        debug_log(f"FEHLER Formatieren (KeyError) Text '{key}'. Schlüssel nicht in Translations oder erfordert Formatierung, die nicht angewendet werden kann.")
        return key # Rohen Schlüssel zurückgeben
    except Exception as e: # Andere Formatierungsfehler (z.B. falsche Anzahl Argumente für einen gefundenen String)
        debug_log(f"FEHLER Formatieren Text '{key}': {e} - Übersetzter Text war: '{translated}'")
        return translated # Gib den (potenziell problematischen) übersetzten String zurück oder den Schlüssel

# --- Windows Dark Mode Erkennung ---
def check_windows_dark_mode():
    if not CAN_CHECK_REGISTRY: # Diese globale Variable prüft, ob 'winreg' überhaupt importiert werden konnte
        print("INFO: check_windows_dark_mode: Registry-Check nicht möglich (Modul 'winreg' nicht importiert). System-Theme wird als 'light' interpretiert.")
        return False # Nimm 'light' an, wenn Registry nicht geprüft werden kann
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        # Öffne den Registry Key
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        # Lese den Wert 'AppsUseLightTheme'. Wenn dieser 0 ist, ist Dark Mode für Apps aktiv.
        value, regtype = winreg.QueryValueEx(registry_key, 'AppsUseLightTheme')
        winreg.CloseKey(registry_key)
        
        is_dark = (value == 0) # value == 0 bedeutet AppsUseLightTheme ist AUS -> Dark Mode ist AN
                               # value == 1 bedeutet AppsUseLightTheme ist AN  -> Light Mode ist AN
        
        print(f"INFO: check_windows_dark_mode: Windows Registry 'AppsUseLightTheme' Wert = {value}. System-Apps sind daher {'dunkel' if is_dark else 'hell'}.")
        return is_dark
    except FileNotFoundError:
        # Dieser Fehler tritt auf, wenn der Schlüssel oder der Wert nicht existiert.
        print(f"INFO: check_windows_dark_mode: DarkMode Registry-Schlüssel '{key_path}' oder Wert 'AppsUseLightTheme' nicht gefunden. System-Theme wird als 'light' interpretiert.")
        return False
    except Exception as e:
        print(f"FEHLER: check_windows_dark_mode: Unerwarteter Fehler beim Lesen des DarkMode Registry-Wertes: {e}. System-Theme wird als 'light' interpretiert.")
        return False

# Fix für ttk Treeview Style Bug mit Themes
def _fixed_map(option):
    global style;
    if not style: print("WARNUNG: Style nicht initialisiert in _fixed_map"); return []
    try: return [elm for elm in style.map("Treeview", query_opt=option) if elm[:2] != ("!disabled", "!selected")]
    except Exception as e: debug_log(f"Fehler in _fixed_map '{option}': {e}"); return []

# --- Speichert Config ---
def save_config_to_file():
    global config; debug_log(f"Schreibe INI: {CONFIG_FILE}")
    try:
        if config.has_section('Settings'):
            if config.has_option('Settings', 'checkcycle'): config.remove_option('Settings', 'checkcycle')
            if config.has_option('Settings', 'startdelay'): config.remove_option('Settings', 'startdelay')
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile: config.write(configfile)
        debug_log("...INI schreiben erfolgreich."); return True
    except Exception as e: debug_log(f"FEHLER Schreiben INI: {e}"); messagebox.showerror(translate("Error"), translate("Error writing config file:\n{}").format(e), parent=root); return False

def create_default_ini():
    global config, current_language, current_theme_setting; debug_log("Erstelle Standard-INI Konfig...")
    config = configparser.ConfigParser(inline_comment_prefixes=('#',';'), interpolation=None)
    config.add_section('Settings'); config['Settings']['CheckCycleSec'] = str(DEFAULT_CHECK_CYCLE_SEC); config['Settings']['StartDelaySec'] = str(DEFAULT_START_DELAY_SEC); config['Settings']['Language'] = current_language; config['Settings']['ThemePreference'] = current_theme_setting
    debug_log(f"... Defaults: Cycle={DEFAULT_CHECK_CYCLE_SEC}s, Delay={DEFAULT_START_DELAY_SEC}s, Lang={current_language}, Theme={current_theme_setting}")
    saved = save_config_to_file();
    if not saved: debug_log("!!! FEHLER Erstellen Default-INI!")
    return saved

# --- Lädt Settings und Programme ---
def load_settings_and_programs():
    global config, program_list, check_cycle_sec, start_delay_sec, program_count
    global current_language, current_theme_setting # Stelle sicher, dass diese hier bekannt sind, gelesen werden sie initial woanders
    global check_cycle_var_sec, start_delay_var_sec, tree_programs, language_var, theme_preference_var

    debug_log(f"Befülle GUI mit Werten aus Config-Objekt und lade Programmliste...")
    program_list = []; program_count = 0

    if tree_programs:
         try: [tree_programs.delete(item) for item in tree_programs.get_children()]
         except Exception as e: debug_log(f"Fehler Leeren Treeview: {e}")
    try:
        check_cycle_sec = config.getint('Settings', 'CheckCycleSec', fallback=DEFAULT_CHECK_CYCLE_SEC)
        start_delay_sec = config.getint('Settings', 'StartDelaySec', fallback=DEFAULT_START_DELAY_SEC)
        # Sprache und Theme werden jetzt initial woanders geladen und von on_language_changed / on_theme_preference_changed gehandhabt
        # current_language = config.get('Settings', 'Language', fallback='de') # Nicht mehr hier lesen
        # current_theme_setting = config.get('Settings', 'ThemePreference', fallback='system').lower() # Nicht mehr hier lesen

        if check_cycle_sec < 1: check_cycle_sec = 1
        if start_delay_sec < 0: start_delay_sec = 0
    except Exception as e: debug_log(f"FEHLER Verarbeiten [Settings] aus config: {e}. Verwende Defaults."); check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC; start_delay_sec = DEFAULT_START_DELAY_SEC

    debug_log(f"Settings für GUI: Cycle={check_cycle_sec}s, Delay={start_delay_sec}s, Lang={current_language}, ThemePref='{current_theme_setting}'")
    if check_cycle_var_sec: check_cycle_var_sec.set(str(check_cycle_sec))
    if start_delay_var_sec: start_delay_var_sec.set(str(start_delay_sec))
    if language_var: # Wird durch on_language_changed und initial load gesetzt
        display_name_lang = next((name for name, code in supported_languages.items() if code == current_language), "Deutsch")
        language_var.set(display_name_lang)
    if theme_preference_var: theme_preference_var.set(current_theme_setting)

    prog_sections = [s for s in config.sections() if s.lower().startswith('program')]
    def get_prog_num(section_name): num_part = section_name[7:]; return int(num_part) if num_part.isdigit() else 9999
    try: prog_sections.sort(key=get_prog_num)
    except ValueError: debug_log("Warnung: Konnte Sektionen nicht sortieren.")
    for section_name in prog_sections:
        try:
            name = config.get(section_name, 'Name', fallback='').strip(); path = config.get(section_name, 'Path', fallback='').strip(); enabled = config.getboolean(section_name, 'Enabled', fallback=False)
            if name and path:
                program_list.append({'name': name, 'path': path, 'enabled': enabled, 'section': section_name}); program_count += 1
                if tree_programs: values = (program_count, name, path, str(enabled)); tree_programs.insert("", tk.END, iid=section_name, values=values, tags=('disabled_row',) if not enabled else ())
        except Exception as e: debug_log(f"FEHLER Lesen Sektion {section_name}: {e}")
    if tree_programs:
        try: tree_programs.tag_configure('disabled_row', foreground='gray')
        except Exception as e: debug_log(f"Fehler Konfig Treeview-Tag: {e}")
    debug_log(f"Programmliste Ladevorgang abgeschlossen. {program_count} Programme.");
    if root and root.winfo_exists(): root.after(50, _update_action_buttons_state)
    return True

# --- Speichert Settings ---
def save_settings_from_gui():
    global check_cycle_sec, start_delay_sec, config, current_language, current_theme_setting
    debug_log(">>> Event: Speichern Klick")
    try:
        new_check_cycle_s = int(check_cycle_var_sec.get()); new_start_delay_s = int(start_delay_var_sec.get())
        if new_check_cycle_s < 1: new_check_cycle_s = 1;
        if new_start_delay_s < 0: new_start_delay_s = 0;
        check_cycle_sec = new_check_cycle_s; start_delay_sec = new_start_delay_s
        check_cycle_var_sec.set(str(check_cycle_sec)); start_delay_var_sec.set(str(start_delay_sec))

        debug_log(f"Aktualisiere Settings in Config: CycleSec={check_cycle_sec}, DelaySec={start_delay_sec}, Lang={current_language}, ThemePref={current_theme_setting}")
        if not config.has_section('Settings'): config.add_section('Settings')
        config['Settings']['CheckCycleSec'] = str(check_cycle_sec); config['Settings']['StartDelaySec'] = str(start_delay_sec)
        config['Settings']['Language'] = current_language # current_language wird von on_language_changed aktualisiert
        config['Settings']['ThemePreference'] = current_theme_setting # current_theme_setting von on_theme_preference_changed

        if save_config_to_file(): messagebox.showinfo(translate("Saved"), translate("Settings have been saved."), parent=root)
    except ValueError: messagebox.showerror(translate("Error"), translate("Invalid number in settings."), parent=root)
    except Exception as e: debug_log(f"FEHLER Speichern Settings: {e}"); messagebox.showerror(translate("Error"), translate("Error saving settings:").format(f"\n{e}"), parent=root)

# --- Hilfsfunktion Button-Status ---
def _update_action_buttons_state():
    if not root or not root.winfo_exists() or not tree_programs or not btnRemoveProg or not btnEditProg: return
    try:
        selected_items = tree_programs.selection()
        state = tk.NORMAL if len(selected_items) == 1 else tk.DISABLED
        if btnRemoveProg: btnRemoveProg.config(state=state)
        if btnEditProg: btnEditProg.config(state=state)
    except tk.TclError: pass
    except Exception as e: debug_log(f"Fehler in _update_action_buttons_state: {e}")

# --- Prozess-Management ---
def is_process_running(process_name):
    try:
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'].lower() == process_name.lower(): return True
            except: pass
        return False
    except Exception as e: debug_log(f"FEHLER psutil: {e}"); return False

def start_program(program_path):
    if not os.path.exists(program_path): debug_log(f"FEHLER: Pfad nicht existent: {program_path}"); return False
    try: program_dir = os.path.dirname(program_path); creationflags = subprocess.CREATE_NO_WINDOW if IS_BUNDLED and sys.platform == "win32" else 0; subprocess.Popen([program_path], cwd=program_dir, creationflags=creationflags); debug_log(f"... Startbefehl '{os.path.basename(program_path)}' OK."); return True
    except Exception as e: debug_log(f"FEHLER Starten von {program_path}: {e}"); return False

# --- Watchdog Hauptschleife ---
STATE_WAIT_CHECK = 0; STATE_CHECKING = 1; STATE_WAIT_DELAY = 2
def watchdog_loop(stop_event_thread):
    global watchdog_state, last_check_completion_time, last_program_start_time, current_program_index
    local_check_cycle_sec = float(check_cycle_sec); local_start_delay_sec = float(start_delay_sec)
    current_program_list_for_cycle = program_list[:]
    if not current_program_list_for_cycle: debug_log("Watchdog-Thread: Keine Programme."); root.after(0, update_watchdog_buttons_on_stop); return
    debug_log(f"Watchdog-Thread gestartet. Zyklus: {local_check_cycle_sec:.1f}s, Delay: {local_start_delay_sec:.1f}s")
    watchdog_state = STATE_CHECKING; current_program_index = 0; last_check_completion_time = 0.0; last_program_start_time = 0.0
    while not stop_event_thread.is_set():
        now = time.monotonic(); process_next_state_immediately = False
        current_list_len = len(current_program_list_for_cycle)
        if not current_program_list_for_cycle and watchdog_state != STATE_WAIT_CHECK :
             debug_log("Watchdog: Programmliste leer geworden, gehe zu Warte-Status."); watchdog_state = STATE_WAIT_CHECK; last_check_completion_time = now; process_next_state_immediately = False
        if watchdog_state == STATE_WAIT_CHECK:
            if not current_program_list_for_cycle: last_check_completion_time = now
            elif last_check_completion_time == 0.0: last_check_completion_time = now
            if (now - last_check_completion_time) >= local_check_cycle_sec:
                current_program_list_for_cycle = program_list[:] # Programmliste für diesen Zyklus neu laden
                current_list_len = len(current_program_list_for_cycle)
                if current_list_len > 0: debug_log("Watchdog: Zyklus beginnt..."); current_program_index = 0; watchdog_state = STATE_CHECKING; process_next_state_immediately = True
                else: debug_log("Watchdog: Zyklus, keine Programme. Warte."); last_check_completion_time = now
        elif watchdog_state == STATE_CHECKING:
            process_next_state_immediately = True
            if current_program_index >= current_list_len: debug_log("Watchdog: Zyklus abgeschlossen."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
            else:
                program = current_program_list_for_cycle[current_program_index]
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
                 program_name_delayed = "?";
                 if current_program_index < current_list_len: program_name_delayed = current_program_list_for_cycle[current_program_index]['name']
                 debug_log(f"Watchdog: Startverzögerung '{program_name_delayed}' beendet."); current_program_index += 1; watchdog_state = STATE_CHECKING
                 if current_program_index >= current_list_len: debug_log("Watchdog: Zyklus beendet (nach letztem Delay)."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
            else: process_next_state_immediately = False
        if not process_next_state_immediately:
            wait_time = SHORT_ADLIB_INTERVAL_SEC;
            if watchdog_state == STATE_WAIT_CHECK: time_to_next_check = max(0, local_check_cycle_sec - (now - last_check_completion_time)); wait_time = min(wait_time, time_to_next_check) if last_check_completion_time > 0 else wait_time
            elif watchdog_state == STATE_WAIT_DELAY: time_to_delay_end = max(0, local_start_delay_sec - (now - last_program_start_time)); wait_time = min(wait_time, time_to_delay_end)
            wait_time = max(0.1, wait_time); stopped = stop_event_thread.wait(timeout=wait_time)
            if stopped: break
        elif stop_event_thread.is_set(): break
    debug_log("Watchdog-Thread: Schleife beendet.");
    if root and root.winfo_exists(): root.after(0, update_watchdog_buttons)

# --- GUI Erstellung ---
def create_gui_widgets():
    # help_font aus der global-Deklaration entfernt, da es nicht mehr als separate Variable benötigt wird.
    # Der Font für die Hilfe-Labels wird jetzt über den Style "Help.TLabel" in apply_custom_font_sizes definiert.
    global root, check_cycle_var_sec, start_delay_var_sec, btnSaveConfig, tree_programs
    global inpProgPathAdd, chkEnabledVar, chkEnabledAdd, btnBrowseAdd, btnAddProg, btnRemoveProg
    global btnEditProg, btnStartWatchdog, btnStopWatchdog, btnExitApp, status_bar_text, style # help_font entfernt
    global lblCheckCycle, lblStartDelay, lblLanguage, lblPathAdd, lblTheme, theme_frame, language_combo
    global r_system, r_light, r_dark, theme_preference_var, settings_frame, programs_frame, add_frame, language_var
    global BASE_FONT_SIZE 

    root.title(translate("Watchdog"));
    root.geometry("550x580")
    root.resizable(False, False)
    
    # --- BLOCK ENTFERNT ---
    # Die folgende try-except-Block zur Erstellung von 'help_font' wurde entfernt,
    # da die "(?)"-Labels jetzt den Style "Help.TLabel" verwenden, der in
    # apply_custom_font_sizes (inkl. Font und Farbe) konfiguriert wird.
    # try:
    #     help_font_family = "Calibri" 
    #     if sys.platform == "darwin": help_font_family = "Helvetica Neue"
    #     elif sys.platform.startswith("linux"): help_font_family = "DejaVu Sans"
    #     help_font = tkFont.Font(family=help_font_family, size=max(7, BASE_FONT_SIZE - 1))
    #     debug_log(f"Help-Font erstellt: Family='{help_font_family}', Size={max(7, BASE_FONT_SIZE - 1)}")
    # except Exception as e:
    #     debug_log(f"Fehler beim Erstellen des Help-Fonts: {e}. Verwende generischen Fallback.")
    #     help_font = tkFont.Font(size=max(7, BASE_FONT_SIZE - 1))
    # --- ENDE BLOCK ENTFERNT ---
        
    check_cycle_var_sec = tk.StringVar(root); start_delay_var_sec = tk.StringVar(root)
    chkEnabledVar = tk.BooleanVar(root, value=True); status_bar_text = tk.StringVar(root, value=translate("Ready."))
    
    language_var = tk.StringVar(root) 
    theme_preference_var = tk.StringVar(root, value=current_theme_setting)

    settings_frame = ttk.LabelFrame(root, text=translate("Settings"), padding="10");
    settings_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew");
    settings_frame.columnconfigure(3, weight=1)
    
    lblCheckCycle = ttk.Label(settings_frame, text=translate("Check cycle (s):"));
    lblCheckCycle.grid(row=0, column=0, padx=(5,0), pady=2, sticky="w");
    # Verwendet jetzt den Style "Help.TLabel" (konfiguriert in apply_custom_font_sizes)
    cycle_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", style="Help.TLabel") 
    cycle_help.grid(row=0, column=1, padx=(0,5), pady=2, sticky="w")
    cycle_help.bind("<Button-1>", lambda e: show_help_cycle())
    
    cycle_entry = ttk.Entry(settings_frame, textvariable=check_cycle_var_sec, width=8); # Breite ggf. anpassen
    cycle_entry.grid(row=0, column=2, padx=5, pady=2, sticky="w")
    
    lblStartDelay = ttk.Label(settings_frame, text=translate("Start delay (s):"));
    lblStartDelay.grid(row=1, column=0, padx=(5,0), pady=2, sticky="w");
    # Verwendet jetzt den Style "Help.TLabel"
    delay_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", style="Help.TLabel") 
    delay_help.grid(row=1, column=1, padx=(0,5), pady=2, sticky="w")
    delay_help.bind("<Button-1>", lambda e: show_help_delay())
    
    delay_entry = ttk.Entry(settings_frame, textvariable=start_delay_var_sec, width=8); # Breite ggf. anpassen
    delay_entry.grid(row=1, column=2, padx=5, pady=2, sticky="w")
    
    lblLanguage = ttk.Label(settings_frame, text=translate("Language:"));
    lblLanguage.grid(row=2, column=0, padx=(5,0), pady=2, sticky="w")
    language_combo = ttk.Combobox(settings_frame, textvariable=language_var, values=list(supported_languages.keys()), state="readonly", width=15);
    language_combo.grid(row=2, column=1, columnspan=2, padx=5, pady=2, sticky="w");
    language_combo.bind('<<ComboboxSelected>>', on_language_changed)
    
    lblTheme = ttk.Label(settings_frame, text=translate("Theme:"));
    lblTheme.grid(row=3, column=0, padx=(5,0), pady=2, sticky="w")
    theme_frame = ttk.Frame(settings_frame); theme_frame.grid(row=3, column=1, columnspan=2, padx=5, pady=2, sticky="w")
    r_system = ttk.Radiobutton(theme_frame, text=translate("System"), variable=theme_preference_var, value="system", command=on_theme_preference_changed);
    r_system.pack(side=tk.LEFT, padx=(0,2))
    r_light = ttk.Radiobutton(theme_frame, text=translate("Light"), variable=theme_preference_var, value="light", command=on_theme_preference_changed);
    r_light.pack(side=tk.LEFT, padx=2)
    r_dark = ttk.Radiobutton(theme_frame, text=translate("Dark"), variable=theme_preference_var, value="dark", command=on_theme_preference_changed);
    r_dark.pack(side=tk.LEFT, padx=2)
    
    btnSaveConfig = ttk.Button(settings_frame, text=translate("Save settings"), command=save_settings_from_gui);
    btnSaveConfig.grid(row=0, column=4, rowspan=4, padx=20, pady=5, sticky="ne")

    programs_frame = ttk.LabelFrame(root, text=translate("Programs"), padding="10");
    programs_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
    programs_frame.columnconfigure(0, weight=1);
    programs_frame.rowconfigure(0, weight=1)
    
    columns = ("nr", "name", "path", "enabled");
    tree_programs = ttk.Treeview(programs_frame, columns=columns, show='headings', selectmode='browse')
    tree_programs.heading("nr", text=translate("Nr."));
    tree_programs.heading("name", text=translate("Name (from path)"));
    tree_programs.heading("path", text=translate("Path"));
    tree_programs.heading("enabled", text=translate("Activated"))
    tree_programs.column("nr", width=30, stretch=tk.NO, anchor='e');
    tree_programs.column("name", width=120);
    tree_programs.column("path", width=250);
    tree_programs.column("enabled", width=60, anchor='center')
    
    scrollbar = ttk.Scrollbar(programs_frame, orient=tk.VERTICAL, command=tree_programs.yview);
    tree_programs.configure(yscroll=scrollbar.set)
    tree_programs.grid(row=0, column=0, sticky='nsew');
    scrollbar.grid(row=0, column=1, sticky='ns')
    tree_programs.bind('<<TreeviewSelect>>', on_list_selection_change);
    tree_programs.bind('<Double-1>', on_edit_button_click)
    if style: style.map("Treeview", foreground=_fixed_map("foreground"), background=_fixed_map("background"))

    add_frame = ttk.LabelFrame(root, text=translate("Add program"), padding="10");
    add_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew");
    add_frame.columnconfigure(2, weight=1)
    
    lblPathAdd = ttk.Label(add_frame, text=translate("Path:"));
    lblPathAdd.grid(row=0, column=0, padx=(5,0), pady=2, sticky="w");
    # Verwendet jetzt den Style "Help.TLabel"
    path_add_help = ttk.Label(add_frame, text="(?)", cursor="question_arrow", style="Help.TLabel") 
    path_add_help.grid(row=0, column=1, padx=(0,5), pady=2, sticky="w")
    path_add_help.bind("<Button-1>", lambda e: show_help_path_add())
    
    inpProgPathAdd = ttk.Entry(add_frame, width=50); inpProgPathAdd.grid(row=0, column=2, padx=5, pady=2, sticky="ew");
    btnBrowseAdd = ttk.Button(add_frame, text=translate("..."), width=3, command=on_browse_button_click);
    btnBrowseAdd.grid(row=0, column=3, padx=5, pady=2)
    
    chkEnabledAdd = ttk.Checkbutton(add_frame, text=translate("Activate"), variable=chkEnabledVar);
    chkEnabledAdd.grid(row=1, column=2, padx=5, pady=5, sticky="w");
    btnAddProg = ttk.Button(add_frame, text=translate("Add"), command=on_add_button_click);
    btnAddProg.grid(row=1, column=3, padx=5, pady=5, sticky="e")

    bottom_frame = ttk.Frame(root, padding="10"); bottom_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew"); bottom_frame.columnconfigure(1, weight=1)
    edit_remove_frame = ttk.Frame(bottom_frame); edit_remove_frame.grid(row=0, column=0, sticky="w")
    # Texte für Edit/Remove Buttons angepasst für mehr Klarheit, was sie tun
    btnEditProg = ttk.Button(edit_remove_frame, text=translate("Edit selected"), command=on_edit_button_click, state=tk.DISABLED); btnEditProg.pack(side=tk.TOP, anchor="w", pady=(0, 2))
    btnRemoveProg = ttk.Button(edit_remove_frame, text=translate("Remove selected"), command=on_remove_button_click, state=tk.DISABLED); btnRemoveProg.pack(side=tk.TOP, anchor="w")
    
    start_stop_frame = ttk.Frame(bottom_frame); start_stop_frame.grid(row=0, column=2, sticky="ns")
    btnStartWatchdog = ttk.Button(start_stop_frame, text=translate("Start"), command=on_start_watchdog_click); btnStartWatchdog.pack(side=tk.TOP, anchor="center", pady=(0, 2))
    btnStopWatchdog = ttk.Button(start_stop_frame, text=translate("Stop"), command=on_stop_watchdog_click, state=tk.DISABLED); btnStopWatchdog.pack(side=tk.TOP, anchor="center")
    
    btnExitApp = ttk.Button(bottom_frame, text=translate("Exit"), command=on_exit_button_click); btnExitApp.grid(row=0, column=3, padx=(20, 5), pady=5, sticky="e")

    status_bar = ttk.Label(root, textvariable=status_bar_text, relief=tk.SUNKEN, anchor=tk.W, padding="2 5"); status_bar.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 5))
    root.columnconfigure(0, weight=1); root.rowconfigure(1, weight=1)
    root.protocol("WM_DELETE_WINDOW", WM_CLOSE_HANDLER)

# --- Hilfe-Funktionen ---
def show_help_cycle(): messagebox.showinfo(translate("Help: Check cycle"), translate("Time in seconds (s) the watchdog waits after checking all programs before checking again."), parent=root)
def show_help_delay(): messagebox.showinfo(translate("Help: Start delay"), translate("Time in seconds (s) the watchdog waits after starting a missing program before checking/starting the *next* program in the list."), parent=root)
def show_help_path_add(): messagebox.showinfo(translate("Help: Path"), translate("Full path to the executable (.exe) file.\nThe process name (e.g., 'program.exe') to monitor is extracted automatically."), parent=root)

# --- Event Handler ---
def on_list_selection_change(event=None):
    if root and root.winfo_exists(): root.after(50, _update_action_buttons_state)

def on_browse_button_click():
    debug_log(">>> Event: Browse Add Path Click"); sFilePath = filedialog.askopenfilename( title=translate("Select program"), initialdir=os.path.dirname(inpProgPathAdd.get()) if inpProgPathAdd.get() else application_path, filetypes=[(translate("Executable files"), "*.exe"), (translate("All files"), "*.*")], parent=root ); root.focus_force()
    if sFilePath: normalized_path = os.path.normpath(sFilePath); debug_log(f"Ausgewählt: {normalized_path}"); inpProgPathAdd.delete(0, tk.END); inpProgPathAdd.insert(0, normalized_path)
    else: debug_log("Keine Datei ausgewählt.")

def on_add_button_click():
    debug_log(">>> Event: OnAddButtonClick"); new_path = inpProgPathAdd.get().strip(); new_enabled = chkEnabledVar.get(); debug_log(f"Add: Path='{new_path}', Enabled={new_enabled}")
    if not new_path: messagebox.showwarning(translate("Missing input"), translate("Program path cannot be empty."), parent=root); return
    monitor_name = os.path.basename(new_path);
    if not monitor_name: messagebox.showerror(translate("Error"), translate("Could not extract filename from path."), parent=root); return
    if not monitor_name.lower().endswith(".exe"):
        if not messagebox.askyesno(translate("Warning"), translate("Extracted name '{}' does not seem to be an .exe.\nSave anyway?").format(monitor_name), parent=root): return
    for prog in program_list:
        if prog['name'].lower() == monitor_name.lower(): messagebox.showwarning(translate("Duplicate name"), translate("A program named '{}' (extracted from path) already exists.").format(monitor_name), parent=root); return
    i = 1;
    while True:
        section_name = f"Program{i}"
        if not config.has_section(section_name): break
        i += 1
        if i > 999: messagebox.showerror(translate("Error"), translate("Could not find free program section (limit 999)."), parent=root); return
    debug_log(f"Füge als Sektion hinzu: {section_name}")
    try:
        if not config.has_section(section_name): config.add_section(section_name)
        config.set(section_name, 'Name', monitor_name); config.set(section_name, 'Path', new_path); config.set(section_name, 'Enabled', str(new_enabled))
        if save_config_to_file(): debug_log("INI geschrieben (Add)."); load_settings_and_programs(); inpProgPathAdd.delete(0, tk.END); chkEnabledVar.set(True); messagebox.showinfo(translate("Success"), translate("Program '{}' added.").format(monitor_name), parent=root)
    except Exception as e: debug_log(f"FEHLER Add/Save: {e}"); messagebox.showerror(translate("Error"), translate("Error adding program:").format(f"\n{e}"), parent=root)

def on_remove_button_click():
    debug_log(">>> Event: OnRemoveButtonClick"); selected_items = tree_programs.selection();
    if not selected_items: messagebox.showwarning(translate("No selection"), translate("Please select a program from the list first."), parent=root); return
    selected_iid = selected_items[0]; debug_log(f"Entferne Sektion: {selected_iid}")
    prog_name_to_remove = f"[{selected_iid}]"
    try:
        prog_name_to_remove = config.get(selected_iid, 'Name', fallback=selected_iid)
        if not messagebox.askyesno(translate("Confirm deletion"), translate("Shall program '{}' really be removed?").format(prog_name_to_remove), parent=root): debug_log("Entfernen abgebrochen."); return
        removed = config.remove_section(selected_iid)
        if not removed: debug_log(f"Sektion {selected_iid} nicht entfernt."); messagebox.showerror(translate("Error"), translate("Could not remove section '{}'.").format(selected_iid), parent=root); return
        if save_config_to_file(): debug_log("INI geschrieben (Remove)."); load_settings_and_programs(); messagebox.showinfo(translate("Success"), translate("Program '{}' removed.").format(prog_name_to_remove), parent=root)
    except KeyError:
        debug_log(f"KeyError beim Entfernen/Zugriff auf {selected_iid}. Möglicherweise schon entfernt oder Konfig-Problem.")
        messagebox.showerror(translate("Error"), translate("Could not find program '{}' in configuration to remove.").format(selected_iid), parent=root)
        load_settings_and_programs()
    except Exception as e:
        import traceback; debug_log(f"!!! FEHLER im Remove-Try-Block für Sektion {selected_iid} !!!"); debug_log(f"Exception Typ: {type(e)}"); debug_log(f"Exception Wert: {e}"); print(f"\n--- TRACEBACK Remove von {selected_iid} ---"); traceback.print_exc(); print("--- TRACEBACK ENDE ---\n"); messagebox.showerror(translate("Error"), translate("Error removing program:").format(f"\n{type(e).__name__}: {e}"), parent=root)

def on_edit_button_click(event=None):
    debug_log(">>> Event: OnEditButtonClick"); selected_items = tree_programs.selection()
    if not selected_items or len(selected_items) > 1:
        if event: # Aufruf durch Doppelklick
            focused_item = tree_programs.focus()
            if focused_item:
                selected_items = (focused_item,); tree_programs.selection_set(focused_item) # Auswahl setzen für Konsistenz
            else: 
                # Verwende die korrekten Übersetzungsschlüssel für die Fehlermeldung, falls unterschiedlich
                messagebox.showwarning(translate("Selection Error"), translate("Please select exactly one program to edit."), parent=root)
                return
        else: 
            messagebox.showwarning(translate("Selection Error"), translate("Please select exactly one program to edit."), parent=root)
            return 
    selected_iid = selected_items[0]; debug_log(f"Bearbeite: {selected_iid}")
    
    # Haupt-Try-Block für den gesamten Dialogaufbau und -ablauf
    try:
        current_name = config.get(selected_iid, 'Name', fallback=""); current_path = config.get(selected_iid, 'Path', fallback=""); current_enabled = config.getboolean(selected_iid, 'Enabled', fallback=False)
        
        edit_window = tk.Toplevel(root)
        edit_window.title(translate("Edit: {}").format(current_name)) # Titel zuerst setzen

        # --- Icon für das Bearbeiten-Fenster setzen (HIER EINFÜGEN) ---
        try:
            # icon_path_edit = resource_path('watchdog.ico') # ALTE ZEILE 
            icon_filename_edit = 'watchdog.ico'
            icon_path_edit = get_icon_resource_path(icon_filename_edit) # NEUE ZEILE
            if os.path.exists(icon_path_edit):
                edit_window.iconbitmap(icon_path_edit)
                debug_log(f"Icon für Bearbeiten-Fenster ({current_name}) gesetzt.")
            else:
                debug_log(f"WARNUNG: Icon-Datei für Bearbeiten-Fenster nicht gefunden: {icon_path_edit}")
        except Exception as e_icon_edit:
            debug_log(f"Fehler beim Setzen des Icons für Bearbeiten-Fenster: {e_icon_edit}")
        # --- Ende Icon setzen ---

        edit_window.resizable(False, False)
        edit_window.transient(root)
        edit_window.grab_set() # Muss nach transient(root) und iconbitmap erfolgen, falls Fehler auftreten und das Fenster nicht korrekt modal wird.
                              # Besser ist es oft, grab_set erst kurz vor wait_window() zu setzen, falls der Dialogaufbau fehlschlägt.

        path_var_edit = tk.StringVar(edit_window, value=current_path)
        enabled_var_edit = tk.BooleanVar(edit_window, value=current_enabled)
        
        dialog_frame = ttk.Frame(edit_window, padding="10")
        dialog_frame.pack(expand=True, fill=tk.BOTH)
        dialog_frame.columnconfigure(1, weight=1)
        
        ttk.Label(dialog_frame, text=translate("Name:")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        name_display_label = ttk.Label(dialog_frame, text=current_name, width=40, relief=tk.SUNKEN, anchor="w")
        name_display_label.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        
        ttk.Label(dialog_frame, text=translate("Path:")).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        # Hier wird path_entry korrekt definiert:
        path_entry = ttk.Entry(dialog_frame, textvariable=path_var_edit, width=40)
        path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        def _browse_edit_path():
            edit_window.grab_release() # Fokus vom Edit-Fenster nehmen für den Filedialog
            sFilePath = filedialog.askopenfilename( 
                title=translate("Select Program"), # Korrigierter Schlüssel "Select Program"
                initialdir=os.path.dirname(path_var_edit.get()) if path_var_edit.get() else application_path, 
                filetypes=[(translate("Executable Files"), "*.exe"), (translate("All Files"), "*.*")], # Schlüssel "Executable Files", "All Files"
                parent=edit_window 
            )
            edit_window.grab_set() # Fokus zurück zum Edit-Fenster
            # edit_window.focus_force() # Kann helfen, den Fokus sicher zurückzugeben
            if sFilePath: 
                path_var_edit.set(os.path.normpath(sFilePath))
        
        browse_button_edit = ttk.Button(dialog_frame, text=translate("..."), width=3, command=_browse_edit_path)
        browse_button_edit.grid(row=1, column=2, padx=5, pady=5)
        
        enabled_check_edit = ttk.Checkbutton(dialog_frame, text=translate("Activate"), variable=enabled_var_edit)
        enabled_check_edit.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="w")
        
        button_frame = ttk.Frame(dialog_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=10)
        
        def _save_edit_and_close():
            new_path = path_var_edit.get().strip()
            new_enabled = enabled_var_edit.get()
            if not new_path: 
                messagebox.showerror(translate("Error"), translate("Path cannot be empty."), parent=edit_window)
                return
            new_monitor_name = os.path.basename(new_path)
            if not new_monitor_name: 
                messagebox.showerror(translate("Error"), translate("Could not extract filename from path."), parent=edit_window)
                return
            if not new_monitor_name.lower().endswith(".exe"):
                if not messagebox.askyesno(translate("Warning"), translate("Extracted name '{}' does not seem to be an .exe.\nSave anyway?").format(new_monitor_name), parent=edit_window): 
                    return
            if new_monitor_name.lower() != current_name.lower():
                for prog in program_list:
                    if prog['section'] != selected_iid and prog['name'].lower() == new_monitor_name.lower(): 
                        messagebox.showerror(translate("Error"), translate("Another program named '{}' already exists.").format(new_monitor_name), parent=edit_window)
                        return
            try:
                config.set(selected_iid, 'Name', new_monitor_name)
                config.set(selected_iid, 'Path', new_path)
                config.set(selected_iid, 'Enabled', str(new_enabled))
                if save_config_to_file(): 
                    debug_log(f"INI nach Edit von {selected_iid} gespeichert.")
                    load_settings_and_programs()
                    edit_window.destroy() # Dialog schließen
            except Exception as e_save: 
                debug_log(f"FEHLER Speichern nach Edit: {e_save}")
                messagebox.showerror(translate("Error"), translate("Error saving changes:").format(f"\n{e_save}"), parent=edit_window)
        
        ok_button = ttk.Button(button_frame, text=translate("OK"), command=_save_edit_and_close)
        ok_button.pack(side=tk.LEFT, padx=10)
        
        cancel_button = ttk.Button(button_frame, text=translate("Cancel"), command=edit_window.destroy)
        cancel_button.pack(side=tk.LEFT, padx=10)
        
        path_entry.focus_set() # Jetzt ist path_entry sicher definiert
        
        # edit_window.grab_set() # grab_set besser hier, kurz bevor der Dialog blockiert, um sicherzustellen, dass der Dialog den Fokus hat
                               # und nach allen Widget-Erstellungen. Ist aber oben schon, das ist ok.
        
        edit_window.wait_window() # Blockiert bis der Dialog geschlossen wird.
        
    except Exception as e_dialog: 
        debug_log(f"FEHLER im Edit-Dialog (Haupt-Try-Block): {e_dialog}")
        import traceback
        debug_log(f"TRACEBACK Edit-Dialog: {traceback.format_exc()}")
        messagebox.showerror(translate("Error"), translate("Error opening edit dialog:").format(f"\n{type(e_dialog).__name__}: {e_dialog}"), parent=root)
    debug_log("<<< Event: OnEditButtonClick Ende.")

def on_start_watchdog_click():
    global is_running, watchdog_thread, stop_event; debug_log(">>> Event: OnStartWatchdogClick")
    if not is_running:
        load_settings_and_programs(); # Sicherstellen, dass aktuelle Einstellungen geladen sind
        if not program_list: messagebox.showwarning(translate("No programs"), translate("No programs configured."), parent=root); return
        is_running = True; stop_event = threading.Event(); debug_log("Erstelle/starte Watchdog-Thread...")
        watchdog_thread = threading.Thread(target=watchdog_loop, args=(stop_event,), daemon=True)
        watchdog_thread.start()
        update_watchdog_buttons(); status_bar_text.set(translate("Watchdog running...")) ; debug_log("Watchdog Gestartet.")
    else: debug_log("Watchdog lief bereits.")

def on_stop_watchdog_click():
    global is_running
    debug_log(">>> Event: OnStopWatchdogClick")
    if is_running:
        debug_log("Sende Stop-Signal...")
        if stop_event:
            stop_event.set()
        is_running = False # Sofort als nicht laufend markieren
        update_watchdog_buttons() # Buttons sofort aktualisieren
        status_bar_text.set(translate("Watchdog stopping..."))
        if root and root.winfo_exists():
            root.after(100, _check_thread_stopped)
    else:
        debug_log("Watchdog war bereits gestoppt.")

def _check_thread_stopped():
    global is_running, watchdog_thread # is_running wird hier nur gelesen
    if watchdog_thread and watchdog_thread.is_alive():
        debug_log("Thread läuft noch, warte...")
        if root and root.winfo_exists():
            root.after(500, _check_thread_stopped)
    else:
        # Status nur final setzen, wenn der Stop-Button ihn auf "stoppt..." gesetzt hat
        # UND is_running (global) tatsächlich False ist (als Bestätigung des Stopp-Vorgangs)
        if not is_running and status_bar_text and status_bar_text.get() == translate("Watchdog stopping..."):
            debug_log("Thread beendet (durch Stop-Befehl).")
            watchdog_thread = None
            if status_bar_text: status_bar_text.set(translate("Watchdog stopped."))
            debug_log("Watchdog Gestoppt (Inaktiv).")
            # update_watchdog_buttons() sollte bereits durch on_stop_watchdog_click erfolgt sein
        elif is_running: # Sollte nicht passieren, wenn on_stop_watchdog_click korrekt is_running gesetzt hat
            debug_log("WARNUNG: _check_thread_stopped fand Thread beendet, aber is_running ist noch True.")
            # is_running = False # Korrektur
            # update_watchdog_buttons()
            # if status_bar_text: status_bar_text.set(translate("Watchdog stopped (forced)."))

def update_watchdog_buttons_on_stop(): # Wird vom Watchdog-Thread aufgerufen, wenn er sich selbst beendet (z.B. keine Programme)
    global is_running, watchdog_thread; debug_log("Watchdog-Thread hat sich selbst beendet.");
    if is_running: # Nur wenn er unerwartet gestoppt hat, während GUI ihn als laufend ansah
        is_running = False; watchdog_thread = None;
        if status_bar_text: status_bar_text.set(translate("Watchdog stopped."))
        update_watchdog_buttons() # Buttons aktualisieren

def update_watchdog_buttons():
     if not root or not btnStartWatchdog or not btnStopWatchdog: return
     try:
         start_state = tk.NORMAL if not is_running else tk.DISABLED
         stop_state = tk.NORMAL if is_running else tk.DISABLED
         if btnStartWatchdog: btnStartWatchdog.config(state=start_state)
         if btnStopWatchdog: btnStopWatchdog.config(state=stop_state)
     except Exception as e: debug_log(f"Fehler Update Watchdog-Buttons: {e}")

def on_exit_button_click():
    debug_log(">>> Event: Exit Button Click / Window Close")
    
    # Zuerst dem Watchdog-Thread signalisieren zu stoppen, falls er läuft.
    # Das eigentliche Warten (join) passiert später, nachdem mainloop beendet ist.
    global is_running # Sicherstellen, dass wir die globale Variable meinen
    if is_running and stop_event:
        debug_log("Sende Stop-Signal an Watchdog-Thread...")
        stop_event.set()
        # is_running wird False, wenn der Thread tatsächlich stoppt oder der Stopp-Button gedrückt wird.
        # Hier setzen wir es noch nicht False, das passiert in on_stop_watchdog_click oder _check_thread_stopped.

    if root:
        try:
            debug_log("Versuche, root.quit() aufzurufen, um mainloop zu beenden.")
            root.quit()  # Beendet die mainloop und lässt den Code danach weiterlaufen
            # root.destroy() wird später im finally-Block von __main__ aufgerufen
        except Exception as e:
            debug_log(f"Fehler bei root.quit(): {e}")

# WM_CLOSE_HANDLER bleibt gleich und ruft on_exit_button_click auf
# def WM_CLOSE_HANDLER(): on_exit_button_click()

def WM_CLOSE_HANDLER(): on_exit_button_click()

# --- Event Handler für Sprach- und Theme-Auswahl ---
def on_language_changed(event=None):
    global current_language, config, language_var # Sicherstellen, dass language_var hier bekannt ist
    if not language_var:
        debug_log("FEHLER: language_var nicht initialisiert in on_language_changed.")
        return

    selected_display_name = language_var.get()
    new_lang_code = supported_languages.get(selected_display_name, None)

    # Vergleiche mit der globalen current_language, die den tatsächlich aktiven Sprachcode hält
    if new_lang_code and new_lang_code != current_language:
        debug_log(f"Sprachwechsel angefordert von '{current_language}' zu: {selected_display_name} (Code: {new_lang_code})")
        previous_language_for_config = current_language # Merken für den Fall, dass Speichern fehlschlägt

        load_language(new_lang_code, is_initial_load=False) # is_initial_load=False, da Benutzerinteraktion
        # current_language wird innerhalb von load_language auf den tatsächlich geladenen Code gesetzt (kann Fallback sein)

        debug_log(f"Sprache nach load_language Versuch: '{current_language}' (ursprünglich angefordert: '{new_lang_code}')")

        # Speichere die *tatsächlich aktive* Sprache in der Konfiguration
        # und aktualisiere die GUI nur, wenn sich die Sprache wirklich geändert hat.
        # Dies verhindert unnötige GUI-Updates, wenn z.B. Englisch gewählt wird,
        # en.json fehlschlägt, auf Deutsch zurückgefallen wird (was schon aktiv war).
        if current_language != previous_language_for_config: # Nur wenn sich die Sprache wirklich geändert hat
            try:
                if not config.has_section('Settings'): config.add_section('Settings')
                config.set('Settings', 'Language', current_language) # Speichere die *effektiv geladene* Sprache
                if save_config_to_file():
                    debug_log(f"Spracheinstellung '{current_language}' erfolgreich gespeichert.")
                else:
                    # Rollback der globalen current_language Variable, wenn Speichern fehlschlägt?
                    # Eher nicht, da die Übersetzungen ja schon für current_language geladen sind.
                    # Der Benutzer bekommt aber eine Fehlermeldung vom Speichern.
                    debug_log(f"FEHLER beim Speichern der Spracheinstellung '{current_language}' in der INI-Datei.")
            except Exception as e:
                debug_log(f"FEHLER beim Versuch, Spracheinstellung in Config zu schreiben: {e}")
            
            update_gui_language() # GUI mit der (potenziell Fallback-)Sprache aktualisieren
            # Combobox-Anzeige auf die tatsächlich aktive Sprache aktualisieren, falls Fallback erfolgt ist
            display_name_loaded = next((name for name, code in supported_languages.items() if code == current_language), None)
            if display_name_loaded and language_var.get() != display_name_loaded:
                debug_log(f"Korrigiere Combobox-Anzeige auf: {display_name_loaded}")
                language_var.set(display_name_loaded)
        else:
             debug_log(f"Sprache wurde nicht geändert (blieb '{current_language}'). GUI-Update und Speichern übersprungen.")
             # Wenn die Auswahl des Benutzers (new_lang_code) nicht der current_language entspricht (wegen Fallback),
             # aber current_language sich nicht von previous_language_for_config unterscheidet,
             # dann wurde die Combobox vielleicht nicht zurückgesetzt.
             display_name_should_be = next((name for name, code in supported_languages.items() if code == current_language), None)
             if display_name_should_be and language_var.get() != display_name_should_be:
                 debug_log(f"Combobox-Anzeige ({language_var.get()}) stimmte nicht mit aktiver Sprache ({current_language}) überein. Korrigiere auf {display_name_should_be}.")
                 language_var.set(display_name_should_be)


    elif new_lang_code and new_lang_code == current_language:
        debug_log(f"Ausgewählte Sprache '{new_lang_code}' ('{selected_display_name}') ist bereits aktiv. Keine Aktion.")
    elif not new_lang_code:
        debug_log(f"FEHLER: Konnte keinen gültigen Sprachcode für '{selected_display_name}' finden.")

def on_theme_preference_changed():
    global current_theme_setting, root, style, tree_programs, config, BASE_FONT_SIZE # BASE_FONT_SIZE hier bekannt machen oder übergeben

    if not theme_preference_var: return 
    new_pref = theme_preference_var.get()
    debug_log(f"Theme-Präferenz geändert zu: {new_pref}")

    # actual_theme_to_set bestimmen (basierend auf new_pref und ggf. check_windows_dark_mode)
    # Diese Logik sollte schon korrekt sein, da der Start jetzt funktioniert.
    _actual_theme_to_set = "light" # Default
    if new_pref == "system":
        if check_windows_dark_mode():
            _actual_theme_to_set = "dark"
    elif new_pref == "dark":
        _actual_theme_to_set = "dark"
    # else new_pref == "light", _actual_theme_to_set bleibt "light"

    # Nur fortfahren, wenn sich das anzuwendende Theme tatsächlich ändert ODER
    # wenn die Präferenz sich ändert (um die Präferenz auch zu speichern, wenn das Theme visuell gleich bleibt)
    # ODER wenn "System" gewählt wurde und sich das OS-Theme geändert haben könnte.

    # Herausfinden, welches Theme gerade via sv_ttk aktiv ist (falls sv_ttk eine get_theme Funktion hat)
    # Für dieses Beispiel nehmen wir an, wir müssen es immer neu setzen, wenn die Präferenz wechselt
    # oder wenn bei "System" eine potentielle Änderung vorliegt.

    theme_changed_visually_or_preference_changed = False

    if new_pref != current_theme_setting:
        theme_changed_visually_or_preference_changed = True
    elif new_pref == "system":
        # Prüfen, ob das aktuell von sv_ttk genutzte Theme dem OS-Theme entspricht
        # Dies ist eine vereinfachte Annahme, dass sv_ttk.get_theme() existiert
        try:
            current_applied_svttk_theme = sv_ttk.get_theme() # Versuche aktuelles Theme zu bekommen
            os_theme_is_dark = check_windows_dark_mode()
            expected_theme_for_system = "dark" if os_theme_is_dark else "light"
            if current_applied_svttk_theme != expected_theme_for_system:
                debug_log(f"System-Theme-Anpassung: OS-Theme ist {expected_theme_for_system}, sv_ttk ist {current_applied_svttk_theme}. Korrektur nötig.")
                theme_changed_visually_or_preference_changed = True # Erzwinge Neusetzung
        except AttributeError: # Falls sv_ttk.get_theme() nicht existiert
            debug_log("WARNUNG: sv_ttk.get_theme() nicht verfügbar, Theme wird basierend auf Präferenzwechsel neu gesetzt.")
            if new_pref == current_theme_setting: # Wenn "System" geklickt wurde und schon "System" war
                 theme_changed_visually_or_preference_changed = True # Im Zweifel neu anwenden


    if theme_changed_visually_or_preference_changed:
        try:
            if 'sv_ttk' in sys.modules:
                debug_log(f"Versuche Theme dynamisch auf '{_actual_theme_to_set}' zu setzen (Präferenz war '{new_pref}')...")
                sv_ttk.set_theme(_actual_theme_to_set)
                # ***** NEU: update_idletasks hinzufügen *****
                if root and root.winfo_exists():
                    root.update_idletasks()
                # *******************************************
                debug_log(f"Theme dynamisch auf '{_actual_theme_to_set}' erfolgreich gesetzt. (update_idletasks nach set_theme)")
                
                if style: 
                    apply_custom_font_sizes(BASE_FONT_SIZE) 
                    # ***** NEU: update_idletasks hinzufügen *****
                    if root and root.winfo_exists():
                        root.update_idletasks()
                    # *******************************************
                    debug_log(f"Eigene Schriftanpassungen erneut angewendet für Theme '{_actual_theme_to_set}'. (update_idletasks nach apply_custom)")
                
                # Treeview Styles nach Theme-Wechsel neu anwenden (war schon da)
                if style and tree_programs and ('_fixed_map' in globals()):
                     # ... (dein Code für Treeview-Anpassung, ggf. mit disabled_fg) ...
                     style.map("Treeview", foreground=_fixed_map("foreground"), background=_fixed_map("background"))
                     disabled_fg = "gray" 
                     if _actual_theme_to_set == "dark":
                         disabled_fg = "#707070" 
                     tree_programs.tag_configure('disabled_row', foreground=disabled_fg)
                     debug_log(f"Treeview Style Map und disabled_row Tag (Farbe: {disabled_fg}) nach Theme-Wechsel neu angewendet.")
            else:
                debug_log("WARNUNG: sv_ttk nicht verfügbar für dyn. Theme-Wechsel.")

            # Die globale Präferenz aktualisieren und speichern
            current_theme_setting = new_pref 
            if not config.has_section('Settings'): config.add_section('Settings')
            config['Settings']['ThemePreference'] = current_theme_setting
            if save_config_to_file():
                debug_log(f"Theme-Präferenz '{current_theme_setting}' gespeichert.")
        except tk.TclError as e:
            debug_log(f"TclError dyn. Setzen Theme oder Schriftanpassung: {e}")
        except Exception as e:
            debug_log(f"Allg. FEHLER dyn. Setzen Theme oder Schriftanpassung: {e}"); import traceback; traceback.print_exc()
    else:
        debug_log(f"Theme-Präferenz '{new_pref}' ist bereits aktiv und System-Theme-konform. Keine Aktion.")

def update_gui_language():
    debug_log("Aktualisiere GUI-Texte für Sprache: " + current_language)
    if not root or not root.winfo_exists():
        debug_log("FEHLER: update_gui_language ohne gültiges root-Fenster aufgerufen.")
        return
    try:
        if root: root.title(translate("Watchdog")) # Stelle sicher, dass dieser Key in allen JSONs existiert
        if settings_frame: settings_frame.config(text=translate("Settings"))
        if programs_frame: programs_frame.config(text=translate("Programs"))
        if add_frame: add_frame.config(text=translate("Add program"))
        if lblCheckCycle: lblCheckCycle.config(text=translate("Check cycle (s):"))
        if lblStartDelay: lblStartDelay.config(text=translate("Start delay (s):"))
        if lblLanguage: lblLanguage.config(text=translate("Language:"))
        if lblPathAdd: lblPathAdd.config(text=translate("Path:"))
        if lblTheme: lblTheme.config(text=translate("Theme:"))
        if btnSaveConfig: btnSaveConfig.config(text=translate("Save settings"))
        if btnAddProg: btnAddProg.config(text=translate("Add"))
        
        # ***** KORREKTUR HIER *****
        if btnRemoveProg: btnRemoveProg.config(text=translate("Remove selected")) # Korrekter Schlüssel
        if btnEditProg: btnEditProg.config(text=translate("Edit selected"))     # Korrekter Schlüssel
        # **************************
        
        if btnStartWatchdog: btnStartWatchdog.config(text=translate("Start Watchdog")) # Überprüfe diesen Schlüssel auch in deinen JSONs
        if btnStopWatchdog: btnStopWatchdog.config(text=translate("Stop Watchdog"))   # Überprüfe diesen Schlüssel auch
        if btnExitApp: btnExitApp.config(text=translate("Exit"))
        if btnBrowseAdd: btnBrowseAdd.config(text=translate("...")) 
        if chkEnabledAdd: chkEnabledAdd.config(text=translate("Activate"))
        if r_system: r_system.config(text=translate("System")) # Schlüssel für Radiobuttons
        if r_light: r_light.config(text=translate("Light"))
        if r_dark: r_dark.config(text=translate("Dark"))
        if tree_programs:
            tree_programs.heading("nr", text=translate("Nr."))
            tree_programs.heading("name", text=translate("Name (from path)"))
            tree_programs.heading("path", text=translate("Path"))
            tree_programs.heading("enabled", text=translate("Activated")) # Oder "Enabled", je nach Konsistenz
        
        current_status = status_bar_text.get()
        # Status nur aktualisieren, wenn er "Bereit." oder ein Äquivalent war, 
        # oder wenn der Watchdog nicht läuft, um Laufmeldungen nicht zu überschreiben.
        # Es ist wichtig, dass der Schlüssel "Ready." in allen JSON-Dateien existiert.
        if is_status_resettable(current_status): # Eine Hilfsfunktion könnte hier nützlich sein
            status_bar_text.set(translate("Ready."))
        # Behalte spezifische Watchdog-Status bei, wenn er läuft und diese anzeigt

        debug_log("GUI-Texte aktualisiert.")
    except Exception as e: 
        debug_log(f"FEHLER Aktualisieren GUI-Texte: {e}"); import traceback; traceback.print_exc()

# Hilfsfunktion (optional, aber empfohlen für den Status-Text)

def is_status_resettable(status_text):
    # Überprüfe, ob der aktuelle Status eine generische Meldung ist, die überschrieben werden kann
    # oder ob der Watchdog nicht läuft.
    if not is_running: # is_running ist deine globale Variable
        return True
    # Prüfe gegen die übersetzten Versionen von "Bereit", "Gestoppt" etc.
    # Diese Schlüssel müssen in deinen JSON-Dateien existieren.
    resettable_keys = ["Ready.", "Watchdog stopped."]
    for key in resettable_keys:
        if status_text == translate(key):
            return True
    return False

# --- Hauptteil ---
if __name__ == "__main__":
    # Dieser erste Print ist OK für das allererste Lebenszeichen im Log.
    print(f"INFO ({time.strftime('%H:%M:%S')}): Watchdog Skript Start (GUI Modus)")

    # Globale Variablen, die hier initialisiert oder referenziert werden.
    # 'config' ist bereits global definiert. BASE_FONT_SIZE sollte auch global sein.
    root = None
    style = None

    # --- SCHRITT 0: Tkinter Hauptfenster EINMALIG erstellen und sofort verstecken ---
    try:
        root = tk.Tk()
        root.withdraw() # Verstecken, bis alles konfiguriert und gestylt ist
        # Verwende debug_log für alle weiteren Logs nach diesem Punkt.
        # Das debug_log System selbst benötigt 'root' nicht für die print-Ausgabe,
        # aber für das Update der Statuszeile, was hier noch nicht relevant ist.
        debug_log(f"Tk Hauptfenster (root) EINMALIG erstellt und initial versteckt.")
    except Exception as e_root_init:
        critical_error_msg = f"Konnte Tkinter-Hauptfenster nicht erstellen: {e_root_init}"
        print(f"KRITISCHER FEHLER: {critical_error_msg}") # Fallback auf print
        try:
            temp_err_root = tk.Tk(); temp_err_root.withdraw()
            messagebox.showerror("Schwerwiegender Fehler", critical_error_msg, parent=None)
            temp_err_root.destroy()
        except: pass
        sys.exit(1)

    # --- SCHRITT 1: Konfigurationsdatei initialisieren/laden (verwendet globales 'config') ---
    if not os.path.exists(CONFIG_FILE):
        debug_log(f"Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden. Erstelle Standard-INI...")
        current_language = 'de'     # Harter Default für Erst-Erstellung
        current_theme_setting = 'system' # Harter Default für Erst-Erstellung
        if not create_default_ini(): # Füllt globales 'config' und speichert; verwendet obige Defaults
            error_msg_cfg = f"Konnte Standard-Konfigurationsdatei nicht erstellen:\n{CONFIG_FILE}\nAnwendung kann nicht starten."
            debug_log(f"KRITISCHER FEHLER: {error_msg_cfg}")
            if root: messagebox.showerror("Kritischer Konfigurationsfehler", error_msg_cfg, parent=root)
            else: print(f"KRITISCHER FEHLER (messagebox nicht möglich): {error_msg_cfg}")
            sys.exit(1)
        else:
            debug_log(f"Standard-INI '{CONFIG_FILE}' erfolgreich erstellt. Globale 'config' ist mit Defaults gefüllt.")
    else:
        debug_log(f"Lade Konfiguration aus '{CONFIG_FILE}'...")
        try:
            config.read(CONFIG_FILE, encoding='utf-8') # Lese in globales 'config'-Objekt
            if not config.has_section('Settings'):
                debug_log("WARNUNG: [Settings]-Sektion fehlt in INI. Ergänze mit Defaults im 'config'-Objekt.")
                config.add_section('Settings')
                if not config.has_option('Settings', 'Language'): config.set('Settings', 'Language', 'de')
                if not config.has_option('Settings', 'ThemePreference'): config.set('Settings', 'ThemePreference', 'system')
                if not config.has_option('Settings', 'CheckCycleSec'): config.set('Settings', 'CheckCycleSec', str(DEFAULT_CHECK_CYCLE_SEC))
                if not config.has_option('Settings', 'StartDelaySec'): config.set('Settings', 'StartDelaySec', str(DEFAULT_START_DELAY_SEC))
            debug_log(f"Konfiguration aus '{CONFIG_FILE}' in globales 'config'-Objekt geladen.")
        except configparser.Error as e_cfg_read:
            error_msg_read = f"Fehler beim Lesen von '{CONFIG_FILE}':\n{e_cfg_read}\n\nStandardwerte werden verwendet."
            debug_log(f"KONFIGURATIONSFEHLER: {error_msg_read}")
            if root: messagebox.showerror("Konfigurationsfehler", error_msg_read, parent=root)
            else: print(f"KONFIGURATIONSFEHLER (messagebox nicht möglich): {error_msg_read}")
            config.clear(); config.add_section('Settings')
            config['Settings']['Language'] = 'de'; config['Settings']['ThemePreference'] = 'system'
            config['Settings']['CheckCycleSec'] = str(DEFAULT_CHECK_CYCLE_SEC); config['Settings']['StartDelaySec'] = str(DEFAULT_START_DELAY_SEC)

    # --- SCHRITT 2: Globale Sprach- und Theme-Präferenzen aus 'config' setzen ---
    try:
        current_language = config.get('Settings', 'Language', fallback='de')
        current_theme_setting = config.get('Settings', 'ThemePreference', fallback='system').lower()
        if current_language not in supported_languages.values():
            debug_log(f"Warnung: Ungültige Sprache '{current_language}' in Config. Fallback auf 'de'.")
            current_language = 'de'
        if current_theme_setting not in ["system", "light", "dark"]:
            debug_log(f"Warnung: Ungültige Theme-Präferenz '{current_theme_setting}' in Config. Fallback auf 'system'.")
            current_theme_setting = "system"
        debug_log(f"Start-Einstellungen (aus Config gelesen): Aktive Sprache='{current_language}', Theme-Präferenz='{current_theme_setting}'")
        load_language(current_language, is_initial_load=True) 
    except Exception as e_prefs:
        debug_log(f"FEHLER beim Setzen der Start-Präferenzen aus Config: {e_prefs}. Verwende harte Defaults.")
        current_language = 'de'; current_theme_setting = 'system'
        load_language(current_language, is_initial_load=True)

    # --- SCHRITT 3: Globale Font Overrides via Tk Resource Database setzen ---
    # BASE_FONT_SIZE ist global definiert (z.B. 8 oder 9)
    font_family_for_override = "Calibri" 
    if sys.platform == "darwin": font_family_for_override = "Helvetica Neue"
    elif sys.platform.startswith("linux"): font_family_for_override = "DejaVu Sans"
    
    font_spec_for_override = f"{{{font_family_for_override}}} {BASE_FONT_SIZE}"

    if root: # Nur ausführen, wenn root erfolgreich erstellt wurde
        root.option_add("*TEntry.font", font_spec_for_override)
        root.option_add("*TCombobox.font", font_spec_for_override)
        root.option_add("*TCombobox*Listbox.font", font_spec_for_override)
        root.option_add("*TRadiobutton.font", font_spec_for_override)
        root.option_add("*TButton.font", font_spec_for_override)
        root.option_add("*TLabel.font", font_spec_for_override)
        root.option_add("*Treeview.font", font_spec_for_override)
        # Treeview.Heading wird separat in apply_custom_font_sizes behandelt
        debug_log(f"Globale Font Overrides via root.option_add gesetzt mit: {font_spec_for_override}")
    else:
        debug_log("FEHLER: root nicht initialisiert, globale Font Overrides übersprungen.")

    # --- SCHRITT 4: Fenster-Icon setzen ---
    try:
        # icon_path = resource_path('watchdog.ico') # ALTE ZEILE
        icon_filename = 'watchdog.ico'
        icon_path = get_icon_resource_path(icon_filename) # NEUE ZEILE
        debug_log(f"Versuche Icon zu laden von: {icon_path}")
        if os.path.exists(icon_path) and root:
            root.iconbitmap(icon_path)
            debug_log("Fenster-Icon gesetzt.")
        elif not os.path.exists(icon_path):
            debug_log(f"WARNUNG: Icon-Datei nicht gefunden: {icon_path}")
    except Exception as e_icon:
        debug_log(f"Fehler beim Setzen des Icons: {e_icon}")

    # --- SCHRITT 5: Tatsächliches initiales Theme bestimmen und mit sv_ttk setzen ---
    actual_theme_to_set = "light" 
    debug_log(f"Bestimme initiales Theme: Aktuelle Theme-Präferenz='{current_theme_setting}'")
    if current_theme_setting == "system":
        debug_log("Theme-Präferenz ist 'system'. Prüfe Windows Dark Mode...")
        system_is_dark = check_windows_dark_mode()
        if system_is_dark: actual_theme_to_set = "dark"
        debug_log(f"System-Theme erkannt als: {'dunkel' if system_is_dark else 'hell'}. Zu setzendes Theme: '{actual_theme_to_set}'.")
    elif current_theme_setting == "dark":
        actual_theme_to_set = "dark"
        debug_log(f"Theme-Präferenz ist 'dark'. Setze Theme auf '{actual_theme_to_set}'.")
    elif current_theme_setting == "light": # Expliziter Check für Klarheit
        actual_theme_to_set = "light"
        debug_log(f"Theme-Präferenz ist 'light'. Setze Theme auf '{actual_theme_to_set}'.")
    
    try:
        if 'sv_ttk' in sys.modules and root:
            debug_log(f"Setze sv_ttk Theme initial auf: '{actual_theme_to_set}'...")
            sv_ttk.set_theme(actual_theme_to_set) 
            debug_log(f"sv_ttk Theme initial auf '{actual_theme_to_set}' gesetzt.")
        elif not root:
             debug_log("FEHLER: root nicht initialisiert vor sv_ttk.set_theme()")
    except Exception as e_theme_init:
        debug_log(f"FEHLER beim initialen Setzen des sv_ttk Themes: {e_theme_init}")

    # --- SCHRITT 6: Globale Styles (ttk.Style) initialisieren und spezifische Anpassungen ---
    debug_log(f"Initialisiere GUI-Styles: Angewandtes Theme='{actual_theme_to_set}' (Präferenz='{current_theme_setting}').")
    try: 
        if root: 
            style = ttk.Style(root)
            
            # Verwende die fokussierte Version von apply_custom_font_sizes
            apply_custom_font_sizes(BASE_FONT_SIZE) 

            if '_fixed_map' in globals():
                try:
                    style.map("Treeview", foreground=_fixed_map("foreground"), background=_fixed_map("background"))
                    debug_log("Treeview Style Map erfolgreich angewendet.")
                except Exception as e_tv_map:
                    debug_log(f"Fehler beim Anwenden der Treeview Style Map: {e_tv_map}")
            debug_log("Spezifische Styles (Help.TLabel, Treeview.Heading) via apply_custom_font_sizes angewendet.")
        else:
            raise Exception("root-Fenster wurde nicht korrekt initialisiert für Style-Anwendung.")
    except Exception as e_style_init:
        debug_log(f"FEHLER bei Style-Initialisierung oder Schriftanpassung: {e_style_init}")

    # --- SCHRITT 7: GUI-Widgets erstellen und Hauptschleife starten ---
    try:
        if not root: # Sollte nicht passieren, wenn die Logik oben korrekt ist
            raise Exception("root-Fenster ist None vor create_gui_widgets.")

        create_gui_widgets() 
        load_settings_and_programs()
        update_watchdog_buttons()
        
        root.deiconify() # Fenster jetzt anzeigen

        debug_log("Plane automatischen Watchdog-Start...")
        root.after(100, on_start_watchdog_click)

        root.mainloop()  
        debug_log("...mainloop() ist beendet (nach root.quit()).")

    except Exception as e_gui_critical:
        debug_log(f"Kritischer Fehler während GUI-Laufzeit oder beim Beenden: {e_gui_critical}")
        import traceback; traceback.print_exc()
        if root and root.winfo_exists():
             try: debug_log("Versuche, root im Fehlerfall zu zerstören..."); root.destroy()
             except Exception as e_destroy: debug_log(f"Fehler beim Zerstören des Fensters im Fehlerfall: {e_destroy}")
        try:
            temp_err_root = tk.Tk(); temp_err_root.withdraw()
            messagebox.showerror("Schwerwiegender Laufzeitfehler", f"Ein schwerwiegender Fehler ist aufgetreten:\n\n{e_gui_critical}\n\nTraceback:\n{traceback.format_exc()}", parent=None) # parent=None für Notfall
            temp_err_root.destroy()
        except: pass # Letzter Versuch, falls auch das scheitert
    finally:
        debug_log("Finale Aufräumarbeiten im __main__ finally-Block...");
        if watchdog_thread and watchdog_thread.is_alive():
            debug_log("Warte auf Beendigung des Watchdog-Threads (join)...");
            if stop_event and not stop_event.is_set():
                debug_log("Setze stop_event im finally-Block (zur Sicherheit, falls noch nicht erfolgt).")
                stop_event.set()
            join_timeout = (SHORT_ADLIB_INTERVAL_SEC * 2) + 0.5 
            watchdog_thread.join(timeout=join_timeout)
            
            if watchdog_thread.is_alive():
                debug_log(f"WARNUNG: Watchdog-Thread wurde nicht innerhalb des {join_timeout:.1f}s Timeouts beendet.")
        elif is_running: 
            debug_log("Hinweis: is_running war True, aber Watchdog-Thread nicht aktiv/auffindbar für join im finally-Block.")
        else:
            debug_log("Watchdog-Thread war beim finalen Aufräumen nicht aktiv oder nicht gestartet.")

        if root: 
            try:
                if root.winfo_exists(): 
                    debug_log("Zerstöre Hauptfenster (root.destroy()) im finalen finally-Block...")
                    root.destroy() 
                else:
                    debug_log("Hauptfenster wurde bereits zerstört oder nicht korrekt initialisiert.")
            except Exception as e_destroy_final:
                debug_log(f"Fehler beim finalen Zerstören des Fensters: {e_destroy_final}")
        
        debug_log("Watchdog Skript Ende (nach __main__ finally-Block).")