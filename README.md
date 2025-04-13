# watchdog
Pythonscript for monitoring and (re)starting programs.

After compilation intended for execution under Windows.

Python and pyinstaller for Windows are required to create and compile the program.

Zum kompilieren von Python in eine einzelne .exe-Datei, die alle Abhängigkeiten beinhaltet:
pyinstaller --onefile --windowed --icon="watchdog.ico" --add-data="watchdog.ico;." watchdog.py
