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
import sv_ttk

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
BASE_FONT_SIZE = 10

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
current_language = "de"
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

def get_base_path():
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = application_path
    return base_path

def get_lang_resource_path(relative_filename):
    base_path = get_base_path()
    return os.path.join(base_path, "lang", relative_filename)

def get_icon_resource_path(relative_filename):
    base_path = get_base_path()
    return os.path.join(base_path, "icon", relative_filename)

def debug_log(message):
    if DEBUG_MODE:
        console_log_message = f"DEBUG ({time.strftime('%H:%M:%S')}): {message}"
        print(console_log_message)

def update_status_message(translation_key, *args, **kwargs):
    message_to_display = translate(translation_key, *args, **kwargs)
    
    if DEBUG_MODE:
        print(f"STATUS_UI ({time.strftime('%H:%M:%S')}): {message_to_display}")

    def _update_status_safe_ui(msg_to_set):
        try:
            if root and root.winfo_exists() and status_bar_text:
                status_bar_text.set(msg_to_set[:120])
        except tk.TclError:
            pass
        except Exception as e_update_ui:
            print(f"STATUS_UPDATE_ERROR: {e_update_ui}")

    if root and status_bar_text:
        current_thread = threading.current_thread()
        main_thread = threading.main_thread()
        if current_thread == main_thread:
            _update_status_safe_ui(message_to_display)
        else:
            root.after(0, _update_status_safe_ui, message_to_display)

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

        treeview_heading_font_spec = (current_font_family, base_size) 
        try:
            style.configure("Treeview.Heading", font=treeview_heading_font_spec, padding=(3, 2)) 
            debug_log(f"Treeview.Heading style konfiguriert mit Font: {treeview_heading_font_spec} und Padding (3,2)")
        except Exception as e_tv_head:
            debug_log(f"Fehler bei Konfiguration des Treeview.Heading Styles: {e_tv_head}")
        
        try:
            font_for_rows = tkFont.Font(family=current_font_family, size=base_size)
            row_height = font_for_rows.metrics("linespace") + 6
            style.configure("Treeview", rowheight=row_height, font=base_font_spec) 
            debug_log(f"Treeview style konfiguriert mit Font: {base_font_spec} und Rowheight: {row_height}")
        except Exception as e_tv_row:
            debug_log(f"Fehler bei Konfiguration des Treeview Styles (rowheight/font): {e_tv_row}")

        try: 
            help_label_font_obj = tkFont.Font(family=current_font_family, size=max(7, base_size - 1))
            style.configure("Help.TLabel", font=help_label_font_obj, foreground="blue")
            debug_log(f"Help.TLabel style konfiguriert mit Font: {help_label_font_obj.actual()}")
        except Exception as e_help_style: 
            debug_log(f"Fehler beim Konfigurieren des Help.TLabel Styles: {e_help_style}")

        try:
            style.configure("TButton", font=base_font_spec)
            debug_log(f"TButton style konfiguriert mit Font: {base_font_spec}")
        except Exception as e_button_style:
            debug_log(f"Fehler bei TButton Style Konfiguration: {e_button_style}")

        try:
            style.configure("TRadiobutton", font=base_font_spec, padding=(3,1)) # Behalte das Padding hier bei
            debug_log(f"TRadiobutton style konfiguriert mit Font: {base_font_spec} und Padding (3,1)")
        except Exception as e_radio_style:
            debug_log(f"Fehler bei TRadiobutton Style Konfiguration: {e_radio_style}")
            
        try:
            style.configure("TCheckbutton", font=base_font_spec, padding=(3,1)) # Behalte das Padding hier bei
            debug_log(f"TCheckbutton style konfiguriert mit Font: {base_font_spec} und Padding (3,1)")
        except Exception as e_check_style:
            debug_log(f"Fehler bei TCheckbutton Style Konfiguration: {e_check_style}")

        debug_log(f"apply_custom_font_sizes (mit Treeview/Button/Radio/Checkbutton Anpassungen) erfolgreich durchlaufen.")

    except Exception as e: 
        debug_log(f"Allgemeiner FEHLER in apply_custom_font_sizes: {e}")
        import traceback
        traceback.print_exc()

# --- Internationalization (i18n) ---
def load_language(lang_code='de', is_initial_load=False):
    global translations, current_language
    original_requested_lang = lang_code
    fallback_order = [lang_code, 'en', 'de']
    seen = set()
    unique_fallback_order = [x for x in fallback_order if not (x in seen or seen.add(x))]

    loaded_successfully = False
    loaded_lang_code = None

    for code_to_try in unique_fallback_order:
        lang_file = get_lang_resource_path(f"{code_to_try}.json")
        debug_log(f"Versuche Sprachdatei zu laden: '{lang_file}' (für ursprünglich angefordertes '{original_requested_lang}')")

        if not os.path.exists(lang_file):
            debug_log(f"WARNUNG: Sprachdatei '{lang_file}' existiert nicht.")
            continue
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                translations = json.load(f)
            current_language = code_to_try
            loaded_lang_code = code_to_try
            debug_log(f"Sprachdatei '{lang_file}' erfolgreich geladen und als '{current_language}' gesetzt.")
            loaded_successfully = True
            break
        except json.JSONDecodeError as e_json:
            debug_log(f"FEHLER: Sprachdatei '{lang_file}' ist fehlerhaft (JSONDecodeError): {e_json}")
        except Exception as e:
            debug_log(f"FEHLER beim Laden/Verarbeiten der Sprachdatei '{lang_file}': {e}")

    if not loaded_successfully:
        debug_log(f"WARNUNG: Keine Sprachdatei konnte für '{original_requested_lang}' oder definierte Fallbacks geladen werden. Setze auf 'de' (hartkodiert) und versuche, 'de.json' zu laden.")
        translations = {}
        current_language = 'de'
        loaded_lang_code = 'de'

        de_lang_file = resource_path("de.json")
        if os.path.exists(de_lang_file):
            try:
                with open(de_lang_file, 'r', encoding='utf-8') as f_de:
                    translations = json.load(f_de)
                debug_log("Fallback auf hartkodiertes 'de.json' erfolgreich geladen.")
            except Exception as e_de_final:
                debug_log(f"FEHLER: Konnte selbst das hartkodierte 'de.json' nicht laden: {e_de_final}")
                translations = {}
        else:
            debug_log("WARNUNG: Hartkodierte Fallback-Sprachdatei 'de.json' existiert nicht. Übersetzungen bleiben leer.")

    if not is_initial_load:
        if loaded_successfully and loaded_lang_code != original_requested_lang:
            if root and root.winfo_exists():
                 messagebox.showwarning(
                    translate("Language load warning"),
                    translate("The selected language '{}' could not be loaded. Switched to '{}'.").format(original_requested_lang, loaded_lang_code),
                    parent=root
                )
        elif not loaded_successfully and original_requested_lang != 'de':
             if root and root.winfo_exists():
                messagebox.showerror(
                    translate("Language load error"),
                    translate("Neither the selected language '{}' nor any fallback languages could be loaded. Defaulting to basic UI text.").format(original_requested_lang),
                    parent=root
                )
    return loaded_successfully

def translate(key, *args, **kwargs):
    translated = translations.get(key, key)
    try:
        if kwargs:
            return translated.format(**kwargs)
        elif args:
            return translated.format(*args)
        else:
            return translated
    except KeyError: 
        debug_log(f"FEHLER Formatieren (KeyError) Text '{key}'. Platzhalter passen nicht oder Schlüssel falsch.")
        return key 
    except Exception as e: 
        debug_log(f"FEHLER Formatieren Text '{key}': {e} - Übersetzter Text war: '{translated}'")
        return translated

# --- Windows Dark Mode Erkennung ---
def check_windows_dark_mode():
    if not CAN_CHECK_REGISTRY:
        print("INFO: check_windows_dark_mode: Registry-Check nicht möglich (Modul 'winreg' nicht importiert). System-Theme wird als 'light' interpretiert.")
        return False
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        value, regtype = winreg.QueryValueEx(registry_key, 'AppsUseLightTheme')
        winreg.CloseKey(registry_key)
        
        is_dark = (value == 0)
        
        print(f"INFO: check_windows_dark_mode: Windows Registry 'AppsUseLightTheme' Wert = {value}. System-Apps sind daher {'dunkel' if is_dark else 'hell'}.")
        return is_dark
    except FileNotFoundError:
        print(f"INFO: check_windows_dark_mode: DarkMode Registry-Schlüssel '{key_path}' oder Wert 'AppsUseLightTheme' nicht gefunden. System-Theme wird als 'light' interpretiert.")
        return False
    except Exception as e:
        print(f"FEHLER: check_windows_dark_mode: Unerwarteter Fehler beim Lesen des DarkMode Registry-Wertes: {e}. System-Theme wird als 'light' interpretiert.")
        return False

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
    global current_language, current_theme_setting
    global check_cycle_var_sec, start_delay_var_sec, tree_programs, language_var, theme_preference_var

    debug_log(f"Lade Einstellungen und Programmliste (Sprache: {current_language}, Theme-Präf.: {current_theme_setting}).")
    program_list = []
    program_count = 0

    if tree_programs:
        try:
            for item in tree_programs.get_children():
                tree_programs.delete(item)
        except Exception as e:
            debug_log(f"Fehler beim Leeren des Treeview: {e}")
    
    try:
        check_cycle_sec = config.getint('Settings', 'CheckCycleSec', fallback=DEFAULT_CHECK_CYCLE_SEC)
        start_delay_sec = config.getint('Settings', 'StartDelaySec', fallback=DEFAULT_START_DELAY_SEC)
        
        if check_cycle_sec < 1: 
            check_cycle_sec = 1
            debug_log(f"CheckCycleSec war < 1, wurde auf 1 korrigiert.")
        if start_delay_sec < 0:
            start_delay_sec = 0
            debug_log(f"StartDelaySec war < 0, wurde auf 0 korrigiert.")

    except Exception as e:
        debug_log(f"FEHLER beim Verarbeiten von [Settings] aus config: {e}. Verwende Standardwerte.")
        check_cycle_sec = DEFAULT_CHECK_CYCLE_SEC
        start_delay_sec = DEFAULT_START_DELAY_SEC
        debug_log(f"GUI-Settings übernommen: Prüfzyklus={check_cycle_sec}s, Startverzögerung={start_delay_sec}s")
    if check_cycle_var_sec: check_cycle_var_sec.set(str(check_cycle_sec))
    if start_delay_var_sec: start_delay_var_sec.set(str(start_delay_sec))
    
    if language_var:
        display_name_lang = next((name for name, code in supported_languages.items() if code == current_language), "Deutsch")
        language_var.set(display_name_lang)
    if theme_preference_var: 
        theme_preference_var.set(current_theme_setting)

    prog_sections = [s for s in config.sections() if s.lower().startswith('program')]
    
    def get_prog_num(section_name):
        num_part = section_name[7:]
        return int(num_part) if num_part.isdigit() else 9999

    try:
        prog_sections.sort(key=get_prog_num)
    except ValueError:
        debug_log("WARNUNG: Konnte Programm-Sektionen nicht numerisch sortieren.")

    for section_name in prog_sections:
        try:
            name = config.get(section_name, 'Name', fallback='').strip()
            path = config.get(section_name, 'Path', fallback='').strip()
            enabled = config.getboolean(section_name, 'Enabled', fallback=False) 
            
            if name and path:
                program_list.append({'name': name, 'path': path, 'enabled': enabled, 'section': section_name})
                program_count += 1
                
                if tree_programs:
                    enabled_key_string = str(enabled) 
                    translated_enabled_string = translate(enabled_key_string) 
                    
                    values = (program_count, name, path, translated_enabled_string)
                    
                    tree_programs.insert("", tk.END, iid=section_name, values=values, tags=('disabled_row',) if not enabled else ())
            else:
                debug_log(f"WARNUNG: Ungültiger oder unvollständiger Eintrag in Sektion {section_name} übersprungen (Name oder Pfad fehlt).")
        except Exception as e:
            debug_log(f"FEHLER beim Lesen der Sektion {section_name}: {e}")
    
    if tree_programs:
        try:
            current_theme_for_disabled_row = sv_ttk.get_theme() if 'sv_ttk' in sys.modules else "light"
            disabled_fg_color = "gray"
            if current_theme_for_disabled_row == "dark":
                disabled_fg_color = "#A0A0A0"
            tree_programs.tag_configure('disabled_row', foreground=disabled_fg_color)
        except Exception as e:
            debug_log(f"Fehler bei der Konfiguration des Treeview-Tags 'disabled_row': {e}")
            
    update_status_message("Status.ProgramListLoadedCount", program_count)
    debug_log(f"Programmliste Ladevorgang abgeschlossen. {program_count} Programme gefunden und geladen.")
    
    if root and root.winfo_exists():
        root.after(50, _update_action_buttons_state)
        
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
        config['Settings']['Language'] = current_language
        config['Settings']['ThemePreference'] = current_theme_setting

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
                current_program_list_for_cycle = program_list[:]
                current_list_len = len(current_program_list_for_cycle)
                if current_list_len > 0:
                    update_status_message("Status.WatchdogCycleStarts")
                    debug_log("Watchdog: Zyklus beginnt...");
                    current_program_index = 0;
                    watchdog_state = STATE_CHECKING;
                    process_next_state_immediately = True
                else:
                    debug_log("Watchdog: Zyklus, keine Programme. Warte.");
                last_check_completion_time = now
        elif watchdog_state == STATE_CHECKING:
            process_next_state_immediately = True
            if current_program_index >= current_list_len: debug_log("Watchdog: Zyklus abgeschlossen."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
            else:
                program = current_program_list_for_cycle[current_program_index]
                if not program['enabled']: current_program_index += 1
                elif is_process_running(program['name']): current_program_index += 1
                else:
                    update_status_message("Status.WatchdogProcessStarting", name=program['name'])
                    debug_log(f"Watchdog: Prozess '{program['name']}' läuft nicht -> Starte...")
                    if start_program(program['path']):
                        update_status_message("Status.WatchdogWaitingAfterStart", delay=f"{local_start_delay_sec:.1f}", name=program['name'])
                        debug_log(f"... Warte {local_start_delay_sec:.1f}s.");
                        last_program_start_time = now;
                        watchdog_state = STATE_WAIT_DELAY;
                        process_next_state_immediately = False
                    else:
                        debug_log(f"... FEHLER Start '{program['name']}'.");
                    current_program_index += 1
                if current_program_index >= current_list_len and watchdog_state == STATE_CHECKING: debug_log("Watchdog: Zyklus beendet (nach Check/Skip)."); last_check_completion_time = now; watchdog_state = STATE_WAIT_CHECK; process_next_state_immediately = False
        elif watchdog_state == STATE_WAIT_DELAY:
            process_next_state_immediately = True
            elapsed_since_start = now - last_program_start_time
            if elapsed_since_start >= local_start_delay_sec:
                 program_name_delayed = "?";
                 if current_program_index < current_list_len: program_name_delayed = current_program_list_for_cycle[current_program_index]['name']
                 update_status_message("Status.WatchdogDelayEndedFor {}", program_name_delayed)
                 debug_log(f"Watchdog: Startverzögerung '{program_name_delayed}' beendet.");
                 current_program_index += 1;
                 watchdog_state = STATE_CHECKING
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
    try:
        if root and root.winfo_exists():
            root.after(0, update_watchdog_buttons)
    except tk.TclError:
        debug_log("Watchdog-Thread: TclError beim Versuch, update_watchdog_buttons via root.after zu planen (wahrscheinlich wird gerade beendet).")
    except RuntimeError as e_runtime:
        if "main thread is not in main loop" in str(e_runtime):
            debug_log("Watchdog-Thread: RuntimeError (main thread not in main loop) beim Versuch, update_watchdog_buttons via root.after zu planen.")
        else:
            debug_log(f"Watchdog-Thread: Unerwarteter RuntimeError: {e_runtime}")
    except Exception as e_after:
        debug_log(f"Watchdog-Thread: Allgemeiner Fehler beim Versuch, update_watchdog_buttons via root.after zu planen: {e_after}")

# --- GUI Erstellung ---
def create_gui_widgets():
    global root, check_cycle_var_sec, start_delay_var_sec, btnSaveConfig, tree_programs
    global inpProgPathAdd, chkEnabledVar, chkEnabledAdd, btnBrowseAdd, btnAddProg, btnRemoveProg
    global btnEditProg, btnStartWatchdog, btnStopWatchdog, btnExitApp, status_bar_text, style
    global lblCheckCycle, lblStartDelay, lblLanguage, lblPathAdd, lblTheme, theme_frame, language_combo
    global r_system, r_light, r_dark, theme_preference_var, settings_frame, programs_frame, add_frame, language_var
    global BASE_FONT_SIZE 

    root.title(translate("Watchdog"));
    root.geometry("550x580")
    root.resizable(False, False)
        
    check_cycle_var_sec = tk.StringVar(root); start_delay_var_sec = tk.StringVar(root)
    chkEnabledVar = tk.BooleanVar(root, value=True); status_bar_text = tk.StringVar(root, value=translate("Ready."))
    
    language_var = tk.StringVar(root) 
    theme_preference_var = tk.StringVar(root, value=current_theme_setting)

    settings_frame = ttk.LabelFrame(root, text=translate("Settings"), padding="10");
    settings_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew");
    settings_frame.columnconfigure(3, weight=1)
    
    lblCheckCycle = ttk.Label(settings_frame, text=translate("Check cycle (s):"));
    lblCheckCycle.grid(row=0, column=0, padx=(5,0), pady=2, sticky="w");
    
    cycle_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", style="Help.TLabel") 
    cycle_help.grid(row=0, column=1, padx=(0,5), pady=2, sticky="w")
    cycle_help.bind("<Button-1>", lambda e: show_help_cycle())
    
    cycle_entry = ttk.Entry(settings_frame, textvariable=check_cycle_var_sec, width=8);
    cycle_entry.grid(row=0, column=2, padx=5, pady=2, sticky="w")
    
    lblStartDelay = ttk.Label(settings_frame, text=translate("Start delay (s):"));
    lblStartDelay.grid(row=1, column=0, padx=(5,0), pady=2, sticky="w");
    
    delay_help = ttk.Label(settings_frame, text="(?)", cursor="question_arrow", style="Help.TLabel") 
    delay_help.grid(row=1, column=1, padx=(0,5), pady=2, sticky="w")
    delay_help.bind("<Button-1>", lambda e: show_help_delay())
    
    delay_entry = ttk.Entry(settings_frame, textvariable=start_delay_var_sec, width=8);
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
        if event:
            focused_item = tree_programs.focus()
            if focused_item:
                selected_items = (focused_item,); tree_programs.selection_set(focused_item)
            else: 
                messagebox.showwarning(translate("Selection Error"), translate("Please select exactly one program to edit."), parent=root)
                return
        else: 
            messagebox.showwarning(translate("Selection Error"), translate("Please select exactly one program to edit."), parent=root)
            return 
    selected_iid = selected_items[0]; debug_log(f"Bearbeite: {selected_iid}")
    
    try:
        current_name = config.get(selected_iid, 'Name', fallback=""); current_path = config.get(selected_iid, 'Path', fallback=""); current_enabled = config.getboolean(selected_iid, 'Enabled', fallback=False)
        
        edit_window = tk.Toplevel(root)
        edit_window.title(translate("Edit: {}").format(current_name))

        try:
            icon_filename_edit = 'watchdog.ico'
            icon_path_edit = get_icon_resource_path(icon_filename_edit)
            if os.path.exists(icon_path_edit):
                edit_window.iconbitmap(icon_path_edit)
                debug_log(f"Icon für Bearbeiten-Fenster ({current_name}) gesetzt.")
            else:
                debug_log(f"WARNUNG: Icon-Datei für Bearbeiten-Fenster nicht gefunden: {icon_path_edit}")
        except Exception as e_icon_edit:
            debug_log(f"Fehler beim Setzen des Icons für Bearbeiten-Fenster: {e_icon_edit}")
        
        edit_window.resizable(False, False)
        edit_window.transient(root)
        edit_window.grab_set()
        
        path_var_edit = tk.StringVar(edit_window, value=current_path)
        enabled_var_edit = tk.BooleanVar(edit_window, value=current_enabled)
        
        dialog_frame = ttk.Frame(edit_window, padding="10")
        dialog_frame.pack(expand=True, fill=tk.BOTH)
        dialog_frame.columnconfigure(1, weight=1)
        
        ttk.Label(dialog_frame, text=translate("Name:")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        name_display_label = ttk.Label(dialog_frame, text=current_name, width=40, relief=tk.SUNKEN, anchor="w")
        name_display_label.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        
        ttk.Label(dialog_frame, text=translate("Path:")).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        path_entry = ttk.Entry(dialog_frame, textvariable=path_var_edit, width=40)
        path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        def _browse_edit_path():
            edit_window.grab_release()
            sFilePath = filedialog.askopenfilename( 
                title=translate("Select Program"),
                initialdir=os.path.dirname(path_var_edit.get()) if path_var_edit.get() else application_path, 
                filetypes=[(translate("Executable Files"), "*.exe"), (translate("All Files"), "*.*")],
                parent=edit_window 
            )
            edit_window.grab_set()
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
                    edit_window.destroy()
            except Exception as e_save: 
                debug_log(f"FEHLER Speichern nach Edit: {e_save}")
                messagebox.showerror(translate("Error"), translate("Error saving changes:").format(f"\n{e_save}"), parent=edit_window)
        
        ok_button = ttk.Button(button_frame, text=translate("OK"), command=_save_edit_and_close)
        ok_button.pack(side=tk.LEFT, padx=10)
        
        cancel_button = ttk.Button(button_frame, text=translate("Cancel"), command=edit_window.destroy)
        cancel_button.pack(side=tk.LEFT, padx=10)
        
        path_entry.focus_set()
        
        edit_window.wait_window()
        
    except Exception as e_dialog: 
        debug_log(f"FEHLER im Edit-Dialog (Haupt-Try-Block): {e_dialog}")
        import traceback
        debug_log(f"TRACEBACK Edit-Dialog: {traceback.format_exc()}")
        messagebox.showerror(translate("Error"), translate("Error opening edit dialog:").format(f"\n{type(e_dialog).__name__}: {e_dialog}"), parent=root)
    debug_log("<<< Event: OnEditButtonClick Ende.")

def on_start_watchdog_click():
    global is_running, watchdog_thread, stop_event; debug_log(">>> Event: OnStartWatchdogClick")
    if not is_running:
        load_settings_and_programs();
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
        is_running = False
        update_watchdog_buttons()
        status_bar_text.set(translate("Watchdog stopping..."))
        if root and root.winfo_exists():
            root.after(100, _check_thread_stopped)
    else:
        debug_log("Watchdog war bereits gestoppt.")

def _check_thread_stopped():
    global is_running, watchdog_thread
    if watchdog_thread and watchdog_thread.is_alive():
        debug_log("Thread läuft noch, warte...")
        if root and root.winfo_exists():
            root.after(500, _check_thread_stopped)
    else:
        if not is_running and status_bar_text and status_bar_text.get() == translate("Watchdog stopping..."):
            debug_log("Thread beendet (durch Stop-Befehl).")
            watchdog_thread = None
            if status_bar_text: status_bar_text.set(translate("Watchdog stopped."))
            debug_log("Watchdog Gestoppt (Inaktiv).")
        elif is_running:
            debug_log("WARNUNG: _check_thread_stopped fand Thread beendet, aber is_running ist noch True.")

def update_watchdog_buttons_on_stop():
    global is_running, watchdog_thread; debug_log("Watchdog-Thread hat sich selbst beendet.");
    if is_running:
        is_running = False; watchdog_thread = None;
        if status_bar_text: status_bar_text.set(translate("Watchdog stopped."))
        update_watchdog_buttons()

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
    
    global is_running
    if is_running and stop_event:
        debug_log("Sende Stop-Signal an Watchdog-Thread...")
        stop_event.set()

    if root:
        try:
            debug_log("Versuche, root.quit() aufzurufen, um mainloop zu beenden.")
            root.quit()
        except Exception as e:
            debug_log(f"Fehler bei root.quit(): {e}")

def WM_CLOSE_HANDLER(): on_exit_button_click()

# --- Event Handler für Sprach- und Theme-Auswahl ---
def on_language_changed(event=None):
    global current_language, config, language_var 
    if not language_var:
        debug_log("FEHLER: language_var nicht initialisiert in on_language_changed.")
        return

    selected_display_name = language_var.get()
    new_lang_code = supported_languages.get(selected_display_name, None)

    if new_lang_code and new_lang_code != current_language:
        debug_log(f"Sprachwechsel angefordert von '{current_language}' zu: {selected_display_name} (Code: {new_lang_code})")
        previous_language_for_config = current_language 

        load_language(new_lang_code, is_initial_load=False) 
        debug_log(f"Sprache nach load_language Versuch: '{current_language}' (ursprünglich angefordert: '{new_lang_code}')")

        if current_language != previous_language_for_config: 
            try:
                if not config.has_section('Settings'): config.add_section('Settings')
                config.set('Settings', 'Language', current_language) 
                if save_config_to_file():
                    debug_log(f"Spracheinstellung '{current_language}' erfolgreich gespeichert.")
                else:
                    debug_log(f"FEHLER beim Speichern der Spracheinstellung '{current_language}' in der INI-Datei.")
            except Exception as e:
                debug_log(f"FEHLER beim Versuch, Spracheinstellung in Config zu schreiben: {e}")
            
            update_gui_language()
            debug_log("Lade Programmliste neu, um Inhalte (z.B. True/False) zu übersetzen...")
            load_settings_and_programs()
            display_name_loaded = next((name for name, code in supported_languages.items() if code == current_language), None)
            if display_name_loaded and language_var.get() != display_name_loaded:
                debug_log(f"Korrigiere Combobox-Anzeige auf: {display_name_loaded}")
                language_var.set(display_name_loaded)

    elif new_lang_code and new_lang_code == current_language:
        debug_log(f"Ausgewählte Sprache '{new_lang_code}' ('{selected_display_name}') ist bereits aktiv. Keine Aktion.")
    elif not new_lang_code:
        debug_log(f"FEHLER: Konnte keinen gültigen Sprachcode für '{selected_display_name}' finden.")

def on_theme_preference_changed():
    global current_theme_setting, root, style, tree_programs, config, BASE_FONT_SIZE

    if not theme_preference_var: return 
    new_pref = theme_preference_var.get()
    debug_log(f"Theme-Präferenz geändert zu: {new_pref}")

    _actual_theme_to_set = "light"
    if new_pref == "system":
        if check_windows_dark_mode():
            _actual_theme_to_set = "dark"
    elif new_pref == "dark":
        _actual_theme_to_set = "dark"
    theme_changed_visually_or_preference_changed = False

    if new_pref != current_theme_setting:
        theme_changed_visually_or_preference_changed = True
    elif new_pref == "system":
        try:
            current_applied_svttk_theme = sv_ttk.get_theme()
            os_theme_is_dark = check_windows_dark_mode()
            expected_theme_for_system = "dark" if os_theme_is_dark else "light"
            if current_applied_svttk_theme != expected_theme_for_system:
                debug_log(f"System-Theme-Anpassung: OS-Theme ist {expected_theme_for_system}, sv_ttk ist {current_applied_svttk_theme}. Korrektur nötig.")
                theme_changed_visually_or_preference_changed = True
        except AttributeError:
            debug_log("WARNUNG: sv_ttk.get_theme() nicht verfügbar, Theme wird basierend auf Präferenzwechsel neu gesetzt.")
            if new_pref == current_theme_setting:
                 theme_changed_visually_or_preference_changed = True


    if theme_changed_visually_or_preference_changed:
        try:
            if 'sv_ttk' in sys.modules:
                debug_log(f"Versuche Theme dynamisch auf '{_actual_theme_to_set}' zu setzen (Präferenz war '{new_pref}')...")
                sv_ttk.set_theme(_actual_theme_to_set)
                if root and root.winfo_exists():
                    root.update_idletasks()
                debug_log(f"Theme dynamisch auf '{_actual_theme_to_set}' erfolgreich gesetzt. (update_idletasks nach set_theme)")
                
                if style: 
                    apply_custom_font_sizes(BASE_FONT_SIZE) 
                    if root and root.winfo_exists():
                        root.update_idletasks()
                    debug_log(f"Eigene Schriftanpassungen erneut angewendet für Theme '{_actual_theme_to_set}'. (update_idletasks nach apply_custom)")
                
                if style and tree_programs and ('_fixed_map' in globals()):
                     style.map("Treeview", foreground=_fixed_map("foreground"), background=_fixed_map("background"))
                     disabled_fg = "gray" 
                     if _actual_theme_to_set == "dark":
                         disabled_fg = "#707070" 
                     tree_programs.tag_configure('disabled_row', foreground=disabled_fg)
                     debug_log(f"Treeview Style Map und disabled_row Tag (Farbe: {disabled_fg}) nach Theme-Wechsel neu angewendet.")
            else:
                debug_log("WARNUNG: sv_ttk nicht verfügbar für dyn. Theme-Wechsel.")

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
        if root: root.title(translate("Watchdog"))
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
        if btnRemoveProg: btnRemoveProg.config(text=translate("Remove selected"))
        if btnEditProg: btnEditProg.config(text=translate("Edit selected"))
        if btnStartWatchdog: btnStartWatchdog.config(text=translate("Start Watchdog"))
        if btnStopWatchdog: btnStopWatchdog.config(text=translate("Stop Watchdog"))
        if btnExitApp: btnExitApp.config(text=translate("Exit"))
        if btnBrowseAdd: btnBrowseAdd.config(text=translate("...")) 
        if chkEnabledAdd: chkEnabledAdd.config(text=translate("Activate"))
        if r_system: r_system.config(text=translate("System"))
        if r_light: r_light.config(text=translate("Light"))
        if r_dark: r_dark.config(text=translate("Dark"))
        if tree_programs:
            tree_programs.heading("nr", text=translate("Nr."))
            tree_programs.heading("name", text=translate("Name (from path)"))
            tree_programs.heading("path", text=translate("Path"))
            tree_programs.heading("enabled", text=translate("Activated"))
        
        current_status = status_bar_text.get()
        if is_status_resettable(current_status):
            status_bar_text.set(translate("Ready."))

        debug_log("GUI-Texte aktualisiert.")
    except Exception as e: 
        debug_log(f"FEHLER Aktualisieren GUI-Texte: {e}"); import traceback; traceback.print_exc()

def is_status_resettable(status_text):
    if not is_running:
        return True
    resettable_keys = ["Ready.", "Watchdog stopped."]
    for key in resettable_keys:
        if status_text == translate(key):
            return True
    return False

# --- Hauptteil ---
if __name__ == "__main__":
    print(f"INFO ({time.strftime('%H:%M:%S')}): Watchdog Skript Start (GUI Modus)")

    root = None
    style = None

    try:
        root = tk.Tk()
        root.withdraw()
        debug_log(f"Tk Hauptfenster (root) EINMALIG erstellt und initial versteckt.")
    except Exception as e_root_init:
        critical_error_msg = f"Konnte Tkinter-Hauptfenster nicht erstellen: {e_root_init}"
        print(f"KRITISCHER FEHLER: {critical_error_msg}")
        try:
            temp_err_root = tk.Tk(); temp_err_root.withdraw()
            messagebox.showerror("Schwerwiegender Fehler", critical_error_msg, parent=None)
            temp_err_root.destroy()
        except: pass
        sys.exit(1)

    if not os.path.exists(CONFIG_FILE):
        debug_log(f"Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden. Erstelle Standard-INI...")
        current_language = 'de'
        current_theme_setting = 'system'
        if not create_default_ini():
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
            config.read(CONFIG_FILE, encoding='utf-8')
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

    font_family_for_override = "Calibri" 
    if sys.platform == "darwin": font_family_for_override = "Helvetica Neue"
    elif sys.platform.startswith("linux"): font_family_for_override = "DejaVu Sans"
    
    font_spec_for_override = f"{{{font_family_for_override}}} {BASE_FONT_SIZE}"

    if root:
        root.option_add("*TEntry.font", font_spec_for_override)
        root.option_add("*TCombobox.font", font_spec_for_override)
        root.option_add("*TCombobox*Listbox.font", font_spec_for_override)
        root.option_add("*TRadiobutton.font", font_spec_for_override)
        root.option_add("*TButton.font", font_spec_for_override)
        root.option_add("*TLabel.font", font_spec_for_override)
        root.option_add("*Treeview.font", font_spec_for_override)
        debug_log(f"Globale Font Overrides via root.option_add gesetzt mit: {font_spec_for_override}")
    else:
        debug_log("FEHLER: root nicht initialisiert, globale Font Overrides übersprungen.")

    try:
        icon_filename = 'watchdog.ico'
        icon_path = get_icon_resource_path(icon_filename)
        debug_log(f"Versuche Icon zu laden von: {icon_path}")
        if os.path.exists(icon_path) and root:
            root.iconbitmap(icon_path)
            debug_log("Fenster-Icon gesetzt.")
        elif not os.path.exists(icon_path):
            debug_log(f"WARNUNG: Icon-Datei nicht gefunden: {icon_path}")
    except Exception as e_icon:
        debug_log(f"Fehler beim Setzen des Icons: {e_icon}")

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
    elif current_theme_setting == "light":
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

    debug_log(f"Initialisiere GUI-Styles: Angewandtes Theme='{actual_theme_to_set}' (Präferenz='{current_theme_setting}').")
    try: 
        if root: 
            style = ttk.Style(root)
            
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

    try:
        if not root:
            raise Exception("root-Fenster ist None vor create_gui_widgets.")

        create_gui_widgets() 
        load_settings_and_programs()
        update_watchdog_buttons()
        
        root.deiconify()

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
            messagebox.showerror("Schwerwiegender Laufzeitfehler", f"Ein schwerwiegender Fehler ist aufgetreten:\n\n{e_gui_critical}\n\nTraceback:\n{traceback.format_exc()}", parent=None)
            temp_err_root.destroy()
        except: pass
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