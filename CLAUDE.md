# watchdog – Projektkontext für Claude Code

- Bei UI-Text-Änderungen alle 7 Sprachdateien unter `lang/` konsistent halten, nicht nur Deutsch/Englisch.
- Ziel ist eine einzelne portable `.exe` ohne Runtime-Abhängigkeiten: bei neuen Features prüfen, ob neue Abhängigkeiten dieses Ziel gefährden.
- Nutzer-facing Texte (Fehlermeldungen, UI): einfache, klare Sprache, die Zielgruppe hat keinen Programmierhintergrund.
- Tag-Format: `vX.Y.Z.W` (vierstellig, z.B. `v1.1.0.0`)
