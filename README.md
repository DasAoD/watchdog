# Watchdog

Python program for monitoring and automatically (re)starting programs.

> I have no programming background and built this entirely with AI support.  
> If that's fine with you — great. If not — no problem either.

---

## Features

- Monitors running processes and restarts them automatically if they stop
- Configurable check interval and start delay
- Multilingual UI: German, English, French, Hungarian, Czech, Spanish, Italian
- Light / Dark / System theme support
- Settings saved in an external `.ini` file
- Compiled as a single standalone `.exe` — no dependencies required

---

## Requirements

To run the program:

- Windows (compiled `.exe` — no Python required)

To build from source:

- Python 3.x
- [PyInstaller](https://pyinstaller.org/)
- Required packages: `psutil`, `sv_ttk`, `tqdm`

Install dependencies:

```
pip install psutil sv_ttk tqdm
```

---

## Build

### Recommended (with progress display and auto-cleanup)

```
python build_script.py
```

The finished `.exe` will be placed in the `Watchdog/` folder.  
A detailed build log is saved to the `log/` folder.

### Manual (PyInstaller directly)

```
pyinstaller watchdog.spec
```

The `.spec` file automatically bundles the icon and all language files into the single `.exe`.

---

## Configuration

Program settings are stored in `watchdog.ini`, located next to the `.exe`.  
The file is created automatically on first launch.

---

## Project Structure

```
watchdog/
├── icon/               # Application icon
├── lang/               # Language files (JSON)
│   ├── de.json
│   ├── en.json
│   ├── fr.json
│   ├── hu.json
│   ├── cz.json
│   ├── es.json
│   └── it.json
├── watchdog.py         # Main application
├── watchdog.spec       # PyInstaller spec (bundles icon + lang files)
├── build_script.py     # Build helper script
├── version.txt         # Windows version info for the .exe
└── watchdog.ini        # Runtime config (created on first launch, not in repo)
```

---

## Roadmap

- [ ] Multiplatform support (Linux, macOS)
- [ ] External config file support (separate from hardcoded values)
- [ ] Structured logging (restarts, errors, process status)
- [ ] Notifications on restart or failure (e-mail, webhook, Telegram)
- [ ] Extended check types (services, TCP ports, HTTP endpoints)
- [ ] Backoff and restart loop protection

---

## Mitwirkende

Dieses Projekt wurde in Zusammenarbeit mit [Claude](https://claude.ai) (Sonnet 4.6) von [Anthropic](https://anthropic.com) entwickelt und iterativ ausgebaut.  
Der überwiegende Teil des Codes, der Architektur und der Dokumentation wurde durch KI generiert und gemeinsam verfeinert.

| Rolle | Person / Tool |
|---|---|
| Projektidee, Anforderungen & Tests | [DasAoD](https://git.uliana.de/DasAoD) |
| Code, Architektur, Dokumentation | [Claude](https://git.uliana.de/Claude) (Anthropic) |

## License

[MIT](LICENSE)

---

## Screenshot

![Watchdog Screenshot](https://github.com/user-attachments/assets/3858bf17-6a7e-4585-9b75-5785bca8b632)
