# watchdog – Projektkontext für Claude Code

Windows-Programm in Python zum Überwachen und automatischen (Neu-)Starten von Programmen.

## Tech-Stack
- Python, Windows-Desktop-Anwendung
- Kompiliert als einzelne standalone `.exe` – keine Dependencies zur Laufzeit erforderlich

## Features
- Überwacht laufende Prozesse, startet sie automatisch neu, wenn sie stoppen
- Konfigurierbares Prüfintervall und Startverzögerung
- Mehrsprachige UI: Deutsch, Englisch, Französisch, Ungarisch, Tschechisch, Spanisch, Italienisch
- Light-/Dark-/System-Theme-Unterstützung

## Struktur
- `icon/` – Programm-Icons
- `lang/` – Übersetzungen (7 Sprachen)

## Wichtige Konventionen
- Bei UI-Text-Änderungen: **alle 7 Sprachdateien** unter `lang/` konsistent halten, nicht nur Deutsch/Englisch – fehlende Übersetzungen fallen negativ auf
- Ziel-Build ist eine einzelne portable `.exe` ohne externe Abhängigkeiten – bei neuen Features prüfen, ob dadurch neue Runtime-Dependencies nötig werden, die dieses Ziel gefährden
- Laut README explizit für Nutzer ohne Programmier-Hintergrund gebaut – bei Nutzer-facing Texten (Fehlermeldungen, UI) entsprechend einfache, klare Sprache bevorzugen
