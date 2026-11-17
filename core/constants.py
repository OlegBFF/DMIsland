"""Константы приложения: версия, габариты острова, пути к файлам."""
import os
from pathlib import Path


APP_NAME, APP_VER = 'Island Pro', '5.5'
APP_PUBLISHER = 'OlegBFF'

# Базовые габариты
CH, W, H, TW, TH = 36, 710, 396, 430, 84

CFG_PATH = Path(os.getenv('APPDATA', '.')) / 'Island' / 'config.json'

LOG_PATH = CFG_PATH.parent / 'island.log'

CRASH_PATH = CFG_PATH.parent / 'crash.log'        # нативные падения (faulthandler): access violation и т.п.

DATA_DIR = CFG_PATH.parent

DB_PATH = DATA_DIR / 'island.db'                  # история буфера, полка, напоминания, диалоги ИИ

CLIP_IMG_DIR = DATA_DIR / 'clip_images'           # картинки из буфера обмена (PNG)

REC_TMP_DIR = DATA_DIR / 'rec_tmp'                # временные файлы записи экрана

STATE_PATH = DATA_DIR / 'state.json'              # исходная рабочая область Windows (на случай аварийного выхода)

SHOTS_DIR = Path.home() / 'Pictures' / 'Island'

MAX_HTTP_BYTES = 2 * 1024 * 1024  # Лимит 2 МБ на внешние ответы API

MAX_STREAM_BYTES = 8 * 1024 * 1024  # Лимит на один потоковый ответ ИИ

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
