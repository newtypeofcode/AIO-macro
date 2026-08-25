"""Russian text for the runtime messages, keyed by the English source.

Adding an entry translates a message; leaving one out keeps the English. The
placeholders must survive the translation unchanged and in the same order --
tests/test_messages.py checks every entry and fails if one drifts, because a
dropped %s does not raise, it just prints the wrong thing.
"""
MESSAGES = {
    "OCR unavailable: %s": "OCR недоступен: %s",
    # Stands in for the engine name in the environment strip when core.ocr
    # will not import at all.
    "unavailable": "недоступен",
    "Startup: %s": "Запуск: %s",
    "Target set: %s": "Цель выбрана: %s",
    "Target set: whole screen": "Цель выбрана: весь экран",
    # The target name and the run state, both shown in the status bar.
    "Whole screen": "Весь экран",
    "Idle": "Простой",
    "Recording started -- do the actions, then press stop.":
        "Запись пошла — сделай действия и нажми стоп.",
    "Recording stopped: %d events.": "Запись остановлена, событий: %d.",
    "Recording discarded.": "Запись отброшена.",
    "Could not save recording: %s": "Не удалось сохранить запись: %s",
    "Recording saved as '%s'.": "Запись сохранена как «%s».",
    "Recording '%s' no longer exists -- nothing saved.":
        "Записи «%s» больше нет — ничего не сохранено.",
    "Could not save recording actions: %s":
        "Не удалось сохранить действия записи: %s",
    "Recording '%s': %d action(s) saved.":
        "Запись «%s»: действий сохранено — %d.",
    "Recording '%s': all actions removed -- it will now do nothing.":
        "Запись «%s»: все действия удалены — теперь она ничего не делает.",
    "Recording '%s' reset to the original events.":
        "Запись «%s» возвращена к исходным событиям.",
    "Could not save macro: %s": "Не удалось сохранить макрос: %s",
    "Macro '%s' saved.": "Макрос «%s» сохранён.",
    "Export failed: %s": "Экспорт не удался: %s",
    "Exported '%s': %d image(s), %d recording(s).":
        "Экспортировано «%s»: картинок — %d, записей — %d.",
    "   missing and not included: %s": "   не найдено и не вошло: %s",
    "Import failed: %s": "Импорт не удался: %s",
    "Imported %d image(s), %d recording(s).":
        "Импортировано: картинок — %d, записей — %d.",
    "   kept your existing %s: %s": "   оставлено твоё (%s): %s",
    "   refused %d unexpected entr(y/ies) in the bundle":
        "   отклонено лишних записей в наборе: %d",
    "Exported to %s": "Экспортировано в %s",
    "Target window is not available.": "Окно-цель недоступно.",
    "Click anywhere to capture a coordinate...":
        "Кликни в любом месте, чтобы взять координату...",
    "Coordinate picker failed: %s": "Не удалось взять координату: %s",
    "Picked %d, %d": "Взято %d, %d",
    "Picked colour %s": "Взят цвет %s",
    "Saved image '%s' (%dx%d).": "Картинка «%s» сохранена (%dx%d).",
    "Language: %s": "Язык: %s",
    "Webhook settings updated.": "Настройки вебхука обновлены.",
    "Webhook URL removed.": "Адрес вебхука удалён.",
    # Only the failure branch substitutes, and what it substitutes is a
    # machine code, so success gets a sentence of its own.
    "Webhook test: %s": "Тест вебхука: %s",
    "Webhook test: delivered.": "Тест вебхука: доставлено.",
    "Macro Studio test message.": "Тестовое сообщение от Macro Studio.",
    # What a Send Webhook block would attach, captioned under the preview.
    "text only": "только текст",
    "%dx%d, %.0f KB": "%dx%d, %.0f КБ",
    # The diagnostics panel. Its rows are rendered as plain text with no
    # table of their own on the frontend, and the same rows become the log
    # lines below them, so panel and log always name a check the same way.
    "Target window": "Окно-цель",
    "not selected": "не выбрано",
    "Screen capture": "Захват экрана",
    "no pixels": "нет пикселей",
    "Synthetic input": "Эмуляция ввода",
    "cursor moved": "курсор сдвинулся",
    "cursor did not move": "курсор не сдвинулся",
    "Display scale": "Масштаб экрана",
    " -- coordinates may drift": " — координаты могут съезжать",
    "OCR engine": "Движок OCR",
    "Recorder hooks": "Перехват для записи",
    "pynput ready": "pynput готов",
    "pynput missing": "pynput не установлен",
    "OK": "норма",
    "FAIL": "сбой",
    "[Health] %s: %s (%s)": "[Проверка] %s: %s (%s)",
    "Macro Studio %s starting...": "Macro Studio %s запускается...",
    "Display scale is %d%% -- coordinates can drift; 100%% recommended.":
        "Масштаб экрана %d%% — координаты могут съезжать; "
        "лучше поставить 100%%.",
    "Global hotkeys unavailable (keyboard package missing).":
        "Глобальные горячие клавиши недоступны (нет пакета keyboard).",
    "Could not bind hotkey %r: %s":
        "Не удалось назначить горячую клавишу %r: %s",
    "Ready. Pick a target window to begin.":
        "Готово. Выбери окно-цель, чтобы начать.",
    "Stopped.": "Прогон остановлен.",
    "Target window disappeared -- stopping so clicks cannot "
    "land on whatever is behind it.":
        "Окно-цель исчезло — останавливаюсь, чтобы клики не попали "
        "в то, что оказалось за ним.",
    "Runner error: %s": "Ошибка выполнения: %s",
    "Run finished.": "Прогон завершён.",
    "Restarted the macro %d times -- giving up.":
        "Макрос перезапускался %d раз — сдаюсь.",
    "Restarting the whole macro (%d).": "Перезапускаю весь макрос (%d).",
    # The two phase headings. Same words the UI uses for its columns, so a
    # log line and the column it talks about name the phase identically.
    "Setup": "Подготовка",
    "Loop": "Цикл",
    "Starting": "Запускаю",
    "Fallback": "Запасные блоки",
    "Run started (%d %s, %d %s blocks).":
        "Прогон начат (блоков: %d в фазе %s, %d в фазе %s).",
    "Target: %s": "Цель: %s",
    "Target window is gone -- using screen coordinates.":
        "Окна-цели нет — работаю по координатам экрана.",
    "Reached %d loop pass(es).": "Пройдено проходов цикла: %d.",
    "Restarted %s %d times without getting "
    "through -- giving up on this pass.":
        "Фаза %s перезапускалась %d раз и так и не прошла до конца — "
        "бросаю этот проход.",
    "   restarting %s from the top (%d)":
        "   перезапускаю %s с начала (%d)",
    "Loop guard tripped -- stopping the run.":
        "Сработала защита от зацикливания — останавливаю прогон.",
    "   - skipped (disabled): %s": "   - пропущен (выключен): %s",
    "   - skipped (ONCE, already ran): %s":
        "   - пропущен (ONCE, уже выполнялся): %s",
    "Loop Start has a bad count -- using 1.":
        "У блока Loop Start неверное число повторов — беру 1.",
    "   ! %s failed: %s": "   ! %s не сработал: %s",
    "   took %.1fs": "   заняло %.1f с",
    "No handler for block type %s": "Нет обработчика для блока типа %s",
    "   (no fallback blocks -- continuing)":
        "   (запасных блоков нет — продолжаю)",
    "   running %d fallback block(s)": "   выполняю запасных блоков: %d",
    "   fallback nested too deep -- skipping":
        "   запасные блоки вложены слишком глубоко — пропускаю",
    "   fallback done -- restarting the phase":
        "   запасные блоки отработали — перезапускаю фазу",
    "   fallback done -- restarting the macro":
        "   запасные блоки отработали — перезапускаю макрос",
    "   fallback done -- stopping":
        "   запасные блоки отработали — останавливаюсь",
    "Unknown key: %r": "Неизвестная клавиша: %r",
    "Found '%s' (%.2f).": "Найдено «%s» (%.2f).",
    "Clicked '%s' at %d,%d (%.2f).": "Клик по «%s» в %d,%d (%.2f).",
    "No image named '%s' in Assets -- treating as already gone.":
        "Картинки «%s» нет в Assets — считаю, что её и так не видно.",
    # Why a Vision block gave up. These are the lines someone reads when the
    # macro stopped doing what it used to do, so they say what was looked
    # for and what happened instead of it.
    "No image named '%s' in Assets -- capture it first.":
        "Картинки «%s» нет в Assets — сначала сними её.",
    "Image '%s' did not appear.": "Картинка «%s» не появилась.",
    "No image named '%s' in Assets -- nothing clicked.":
        "Картинки «%s» нет в Assets — кликать не по чему.",
    "Image '%s' not found -- nothing clicked.":
        "Картинка «%s» не найдена — клика не было.",
    "Image '%s' is still on screen.": "Картинка «%s» всё ещё на экране.",
    "Color %s never appeared at %s,%s.":
        "Цвет %s так и не появился в %s,%s.",
    "Text %r not found.": "Текст %r не найден.",
    "Text %r not found -- nothing clicked.":
        "Текст %r не найден — клика не было.",
    "Colour %s not found -- nothing clicked.":
        "Цвет %s не найден — клика не было.",
    "Text matched exactly: %r": "Текст совпал точно: %r",
    "Text matched: %r (%.2f)": "Текст совпал: %r (%.2f)",
    "Clicked text %r at %d,%d (%.2f)": "Клик по тексту %r в %d,%d (%.2f)",
    "Clicked colour %s at %d,%d (%d px)":
        "Клик по цвету %s в %d,%d (%d px)",
    "Read: %r": "Прочитано: %r",
    "Watch": "Наблюдение",
    "Camera: sweeping %d px past the limit (%d x %d,%d).":
        "Камера: веду на %d пкс до упора (%d шагов по %d,%d).",
    "Camera to the limit %s,%s (%s)": "Камера до упора %s,%s (%s)",
    "Nothing to run -- every phase is empty.":
        "Запускать нечего — все фазы пустые.",
    "Watch: %d block(s), checked between steps every %d ms.":
        "Наблюдение: %d блок(ов), проверка между шагами каждые %d мс.",
    "Only the Watch phase has blocks -- monitoring until Stop.":
        "Блоки есть только в фазе Наблюдение — слежу до остановки.",
    "Watch fired (%d).": "Наблюдение сработало (%d).",
    "   watch done -- restarting the whole macro":
        "   наблюдение отработало — перезапускаю весь макрос",
    "   watch done -- restarting the Loop":
        "   наблюдение отработало — перезапускаю Цикл",
    "   watch done -- moving on to the Loop":
        "   наблюдение отработало — перехожу к Циклу",
    "   watch done -- carrying on": "   наблюдение отработало — продолжаю",
    "Macro report": "Отчёт макроса",
    "If / Else (%s)": "Если / иначе (%s)",
    "condition set": "условие задано",
    "condition not set": "условие не задано",
    "While loop (max %d)": "Цикл пока (макс. %d)",
    "Repeat until (max %d)": "Повторять до (макс. %d)",
    "Open app %r": "Открыть приложение %r",
    "Kill process %r": "Завершить процесс %r",
    "Macro Studio test message.": "Тестовое сообщение Macro Studio.",
    "If: condition %s -> %s": "Если: условие %s → %s",
    "Kill Process: %s": "Завершение процесса: %s",
    "Kill Process: no process matching %r found.": "Подходящих процессов для %r не найдено.",
    "Kill Process: no process name given.": "Имя процесса не указано.",
    "Killed: %s": "Завершено: %s",
    "Open App failed: %s": "Не удалось открыть приложение: %s",
    "Open App: no path given.": "Путь к приложению не указан.",
    "Opened: %s": "Открыто: %s",
    "Recorder hook error: %s": "Ошибка перехвата записи: %s",
    "Repeat Until: reached max iterations (%d)": "Повторять до: достигнут лимит итераций (%d)",
    "Repeat: iteration %d": "Повтор: итерация %d",
    "While: iteration %d": "Пока: итерация %d",
    "While: reached max iterations (%d)": "Пока: достигнут лимит итераций (%d)",
    "Runtime": "Время работы",
    "Loop passes": "Проходов цикла",
    "Watch fired": "Сработок наблюдения",
    "Target": "Цель",
    "Attachment": "Вложение",
    "Read text %s %r": "Прочитать текст %s %r",
    "   text check passed: %r %s %r": "   проверка текста пройдена: %r %s %r",
    "Text check failed: %r %s %r": "Проверка текста не прошла: %r %s %r",
    "Text check failed: no number in %r vs %r":
        "Проверка текста не прошла: нет числа в %r или %r",
    "No target window to focus.":
        "Нет окна-цели, которое можно активировать.",
    "Target would not resize to %dx%d -- it is %dx%d.":
        "Цель не приняла размер %dx%d — сейчас %dx%d.",
    "Target now %dx%d at %d,%d.": "Цель теперь %dx%d в точке %d,%d.",
    "Webhook is switched off in Settings -- nothing sent.":
        "Вебхук выключен в настройках — ничего не отправлено.",
    "Webhook URL is not usable (%s) -- nothing sent.":
        "Адрес вебхука не годится (%s) — ничего не отправлено.",
    "Could not capture the %s -- sending text only.":
        "Не удалось снять %s — отправляю только текст.",
    "No saved image named '%s' -- sending text only.":
        "Сохранённой картинки «%s» нет — отправляю только текст.",
    # What the webhook attached, named inside the sentence above.
    "no attachment": "без вложения",
    "image '%s'": "картинка «%s»",
    "target window": "окно-цель",
    "whole screen": "весь экран",
    "region": "область",
    "Webhook sent (%s).": "Вебхук отправлен (%s).",
    "Webhook failed: %s": "Вебхук не отправлен: %s",
    "Playing '%s' (%d edited actions)":
        "Проигрываю «%s» (изменённых действий: %d)",
    "Recording '%s' has an empty action list -- nothing to do.":
        "У записи «%s» пустой список действий — делать нечего.",
    "Recording '%s' is empty.": "Запись «%s» пуста.",
    "Playing '%s' (%d raw events)":
        "Проигрываю «%s» (исходных событий: %d)",
    "pynput is not installed -- recording unavailable.":
        "pynput не установлен — запись недоступна.",
    "Raw mouse input unavailable -- camera drags "
    "will be recorded from cursor positions only.":
        "Raw-ввод мыши недоступен — повороты камеры запишутся только "
        "по позициям курсора.",
    "Raw mouse input unavailable (%s).":
        "Raw-ввод мыши недоступен (%s).",

    # One line per executed block -- the highest-volume text in the log.
    # Worded like the block labels in block_help.py so the trace and the
    # palette chip a reader just dragged in call the same thing by the same
    # name. What is substituted stays as the macro stored it: a button name,
    # a key, a picture name.
    "Click %s,%s (%s%s)": "Клик %s,%s (%s%s)",
    "Move to %s,%s": "Двинуть мышь в %s,%s",
    "Move by %s,%s": "Сместить мышь на %s,%s",
    "Drag from %s to %s,%s (%s)": "Перетащить от %s в %s,%s (%s)",
    "Drag from %s by %s,%s (%s)": "Перетащить от %s на %s,%s (%s)",
    "Look %s,%s x%s (%s)": "Обзор %s,%s x%s (%s)",
    "Place %s on %s at %s,%s": "Поставить %s на %s в %s,%s",
    "Place %s (no location)": "Поставить %s (место не выбрано)",
    "No location picked for the unit.": "Для юнита не выбрано место.",
    "Placed %s at %s,%s": "Поставлен %s в %s,%s",
    "Saved map '%s' (%dx%d).": "Карта «%s» сохранена (%dx%d).",
    "This map picture has no saved geometry -- read as a window shot.":
        "У этой карты не сохранена геометрия — читаю её как "
        "снимок окна.",
    "This map picture has no saved geometry -- read as a whole-screen shot.":
        "У этой карты не сохранена геометрия — читаю её как "
        "снимок всего экрана.",
    # Stands in for the start point in the two lines above when the drag
    # begins wherever the cursor happens to be.
    "cursor": "курсора",
    "Scroll up %d": "Прокрутка вверх %d",
    "Scroll down %d": "Прокрутка вниз %d",
    "Key %s": "Клавиша %s",
    "Hold %s for %sms": "Держать %s %s мс",
    "Type %r": "Напечатать %r",
    "Wait %sms": "Пауза %s мс",
    "Wait %s-%sms": "Пауза %s-%s мс",
    "Wait for image '%s'": "Ждать картинку «%s»",
    "Click image '%s'": "Клик по картинке «%s»",
    "Wait until image '%s' is gone":
        "Ждать, пока картинка «%s» пропадёт",
    "Wait for colour %s at %s,%s": "Ждать цвет %s в %s,%s",
    "Click colour %s": "Клик по цвету %s",
    "Wait for text %r": "Ждать текст %r",
    "Click text %r": "Клик по тексту %r",
    "Read text": "Прочитать текст",
    "Loop start x%s": "Начало цикла x%s",
    "Loop end": "Конец цикла",
    "Play recording '%s'": "Проиграть запись «%s»",
    "Focus target": "Фокус на цель",
    "at %s,%s": "в %s,%s",
    "Log %r": "Журнал %r",
    "Webhook %r%s": "Вебхук %r%s",
    # Rejoin Server, and the two Flow jumps.
    "Rejoin Roblox (%s)": "Переподключение к Roblox (%s)",
    "server from Settings": "сервер из настроек",
    "Restart this phase": "Перезапустить фазу",
    "Restart the macro": "Перезапустить макрос",
    "Rejoin only works on Windows.": "Переподключение работает только в Windows.",
    "Nothing to rejoin with -- paste a share link, or a place id, on the block or in Settings.":
        "Нечем переподключаться — вставь ссылку-приглашение или ID места в блоке либо в настройках.",
    "Closed %d Roblox client(s).": "Закрыто клиентов Roblox: %d.",
    "Rejoining %s...": "Заходим: %s...",
    "share link": "ссылка-приглашение",
    " (private server)": " (приватный сервер)",
    "Could not start the Roblox client.": "Не удалось запустить клиент Roblox.",
    "Roblox did not come back within %ds.": "Roblox не вернулся за %d с.",
    "Roblox is back: %s": "Roblox вернулся: %s",
    "Target switched to the new Roblox window.":
        "Цель переключена на новое окно Roblox.",
    "Block asked to restart the phase.": "Блок просит перезапустить фазу.",
    "Block asked to restart the macro.": "Блок просит перезапустить макрос.",
    # Saved block groups.
    "Block group '%s' saved (%d block(s)).":
        "Группа блоков «%s» сохранена (блоков: %d).",
    "Block group '%s' deleted.": "Группа блоков «%s» удалена.",
    "Could not save the block group: %s": "Не удалось сохранить группу блоков: %s",
}
