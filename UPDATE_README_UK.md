# Встановлення оновлення Discovery 1.1

Цей архів містить тільки нові та змінені файли відносно наданого тобою YouTubeBot.zip.
Повної копії бота тут немає. Нічого видаляти або перейменовувати не потрібно.

1. Закрий бот.
2. Розпакуй архів у тимчасову папку.
3. Виділи ВЕСЬ його вміст і скопіюй безпосередньо в C:\YouTubeBot.
4. Погодься на об’єднання папок та заміну однойменних файлів.
   Наприклад, gui/app.py має замінити C:\YouTubeBot\gui\app.py.
   Не видаляй старі папки gui або queue: решта їхніх файлів потрібна.
5. Якщо це перше встановлення Discovery, запусти INSTALL_DISCOVERY.bat.
6. Прочитай START_HERE_UK.md про Tesseract і перевірку залежностей.
7. Запускай новий модуль через START_DISCOVERY.bat.

config.py, BrowserProfile, бази даних, відео і твої EXE цей архів не містить.
Якщо ти вже встановив повний пакет Discovery 1.1 з попереднього повідомлення,
повторне копіювання цього оновлення не додає нових функцій.

## Змінені файли

- .gitignore
- README.md
- YouTubeBot.spec
- gui/app.py
- main.py
- queue/__init__.py

## Нові файли

- INSTALL_DISCOVERY.bat
- README_LEGACY.md
- START_DISCOVERY.bat
- START_GUI.bat
- START_HERE_UK.md
- check_discovery.py
- config.example.py
- discovery/__init__.py
- discovery/screening.py
- discovery/service.py
- discovery/settings.py
- discovery/sources.py
- discovery/store.py
- discovery_settings.example.json
- requirements-build.txt
- requirements.txt
- run_discovery.py
- run_discovery_gui.py
- tests/test_discovery.py
- UPDATE_README_UK.md — ця інструкція.
