# Island Pro

Динамический остров для Windows: темы, жидкие анимации, плееры, события устройств, игровой режим.

    pip install -r requirements.txt
    python main.py

### Запуск без консоли: лаунчер

`launcher.py` сам находит Python, создаёт окружение в `%LOCALAPPDATA%\\IslandPro\\venv`, ставит библиотеки (повторно — только если
изменился `requirements.txt`), запускает остров без окна консоли и при вылете показывает причину (вывод процесса, `island.log`, `crash.log`).

    Island.pyw          двойной клик, если Python уже установлен
    build_exe.bat       собирает IslandLauncher.exe (PyInstaller) — после этого Python на ПК не нужен для запуска лаунчера

Логи — в `%APPDATA%\\Island`: `run.log` (вывод процесса), `island.log` (исключения, предупреждения Qt/Python),
`crash.log` (нативные падения: стеки всех потоков), `launcher.log`, `last_crash.txt` (последний отчёт о сбое).

## Структура

    main.py               точка входа
    core/                 без Qt-виджетов: константы, конфиг, безопасность, Win32, запуск, хранилища
      constants.py  config.py  utils.py  security.py  win32.py  app.py
      db.py  clipstore.py  stores.py  schedule.py  secrets_detect.py     SQLite, буфер, полка, напоминания, диалоги ИИ
    system/               управление Windows в фоновых потоках (без виджетов)
      hub.py              SystemHub: три воркера и Qt-сигналы с РЕАЛЬНЫМ состоянием системы
      worker.py           поток с очередью команд (одинаковые ключи вытесняют друг друга) и опросом
      audio_ctl  radios  wifi  bluetooth  brightness  power  winmode  util
    ui/                   интерфейс
      island.py           главное окно: собирается из миксинов, цикл анимации, paintEvent
      themes.py  animations.py  icons.py  widgets.py  overlays.py
      settings_dialog.py  tray.py  window.py  control_center.py  reminder_dialog.py  notif_card.py  focus.py
      panels/             страницы острова (home, clip, shelf, text, chat, notes, weather, sys)
    modules/              функции: у каждой — логика и рабочие классы
      media  audio  notifications  system_monitor  clipboard  recorder  weather
      assistant  ai_client  capture  notes  reminders  shelf  text_tools  apps
      notify_center  winnotify  notify_reply   центр уведомлений: приём из Windows, приоритеты, карточка, ответ
      recorder_core  audio_io  spectrum        запись экрана и звука, захват WASAPI, FFT-эквалайзер (без Qt)
    plugins/  database/  assets/   пока пусто
    tests/                python -m unittest discover -s tests -t .

## Как устроен Island

`ui/island.py` — класс `Island(QWidget)`, собранный из миксинов (`modules/*` и `ui/panels/*`).
Каждый миксин отвечает за свою область и обращается к общему состоянию через `s` (как и раньше).
Миксины стоят в списке баз **перед** `QWidget`, поэтому их методы перекрывают одноимённые методы Qt
(например, `grab`, `place`) точно так же, как это делал сам `Island`.
Переопределения событий Qt (`paintEvent`, `mousePressEvent`, `dragEnterEvent`, `dropEvent`) остались в `Island`.

## Слои импортов (циклов нет)

    constants → utils, security, win32 → config → ui/themes, icons, animations → ui/widgets
    → modules/* → ui/panels/*, tray, window, settings_dialog → ui/island → core/app

## Потоки и Qt

Правило: **виджеты и буфер обмена Qt трогает только главный поток.** Рабочие потоки (запись экрана, ИИ, OCR, голос,
загрузка, SystemHub, анализ звука) работают с обычными данными и сообщают результат сигналами.
`system/` и `core/*store*` не импортируют виджеты, поэтому проверяются тестами без Qt и Windows.

## Данные

Всё пользовательское лежит в `%APPDATA%\Island`: `island.db` (SQLite: история буфера, полка, напоминания, диалоги ИИ),
`clip_images/` (картинки из буфера), `state.json` (исходная рабочая область Windows на случай аварийного выхода).
Секреты в истории буфера шифруются через DPAPI, скрываются в списке и удаляются через `clip_secret_ttl` секунд.

## Что нужно на Windows

Запись звука — `pyaudiowpatch` и `imageio-ffmpeg` (он же даёт H.264 и GIF с палитрой), яркость — `screen-brightness-control`,
Wi-Fi/Bluetooth — пакеты `winrt-Windows.Devices.*`. Без любого из них остальное работает, а недостающая функция
сообщает, чего не хватает.

## Центр уведомлений

Остров читает уведомления Windows (`UserNotificationListener`; нужно разрешение в Параметры → Конфиденциальность → Уведомления),
раскладывает их по приоритетам (`core/notif_rules.py`) и сохраняет в историю (`notifications` в `island.db`):

- **Важные** — мессенджеры, звонки, коды подтверждения, ваши приложения и слова: расширенная карточка с отправителем и текстом,
  обводка и чип приоритета, показ 15 с (наведение продлевает), очередь со стрелками.
- **Системные** — Windows Security, обновления, батарея и события самого острова: короткий тост или карточка (настройка).
- **Обычные** — тост, карточка или «только история».

«Не беспокоить» и тихие часы пропускают только важные. В полноэкранном режиме и при записи экрана уведомления копятся и
показываются сводкой. Действия: отложить (5 мин … завтра), открыть приложение, отметить прочитанным, быстрый ответ.

**Быстрый ответ.** Windows не даёт стороннему приложению ответить от имени чужого уведомления, поэтому ответ устроен через
провайдеров (`modules/notify_reply.py`). Встроенный открывает приложение и копирует ответ в буфер (по желанию вставляет Ctrl+V,
Enter нажимаете вы). Настоящий ответ через API мессенджера добавляется как ещё один `ReplyProvider` без правок интерфейса.

## Умное скрытие и масштаб

Остров раскрывается после короткой задержки у грани экрана (случайные касания игнорируются), в развёрнутых окнах сворачивается
в тонкую линию, прячется для выбранных программ и в полноэкранном режиме. Масштаб интерфейса (`ui_scale`) задаётся до старта
через `QT_SCALE_FACTOR`: «Авто» подбирает его по логической ширине монитора.

## Фокус ввода

Окно не активируется кликами (не крадёт фокус), но при клике в поле ввода активируется на время набора и затем возвращает
фокус прежнему окну (`ui/focus.py`). Раньше поля ввода острова клавиатуру не получали.
