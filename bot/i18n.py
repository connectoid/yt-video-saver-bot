from __future__ import annotations

# Языки, которые реально умеет отдавать бот. Порядок здесь же используется
# для порядка кнопок в /language (см. bot/handlers/language.py).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "ru")

# 2026-09-07: Stats.non_ru_users (см. bot/db/crud.py::get_stats, колонка
# User.language_code) показал ~90% пользователей с языком клиента Telegram
# НЕ "ru" — отсюда и появилась эта локализация. English — нейтральный
# дефолт для всех, у кого язык неизвестен (Telegram не прислал
# language_code) или не поддерживается (не "ru"), а не только "en" в узком
# смысле — так и раньше решалось для non_ru_users в статистике.
DEFAULT_LANGUAGE = "en"

# ru намеренно оставлен как есть — переносим текст 1:1 из старого
# докода до локализации, en — новый перевод. Ключи специально совпадают
# между языками построчно, чтобы расхождение было легко заметить в diff.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "welcome": (
            "👋 Привет! Я скачиваю видео и Shorts с YouTube.\n\n"
            "Просто пришли мне ссылку на видео — я покажу превью и предложу "
            "доступные разрешения для скачивания, а также кнопку "
            "\"🎵 Скачать аудио\", если нужен только звук.\n\n"
            "Скачивая видео, вы соглашаетесь с условиями использования — /terms."
        ),
        "help_header": (
            "Как пользоваться:\n"
            "1. Отправь ссылку на видео или Shorts с YouTube.\n"
            "2. Выбери разрешение из предложенных кнопок — или кнопку "
            "\"🎵 Скачать аудио\", если видео не нужно, только звук.\n"
            "3. Дождись, пока я скачаю и пришлю файл.\n\n"
            "Команды:\n"
            "/limits — сколько скачиваний осталось сегодня\n"
            "/history — последние скачанные видео\n"
            "/cancel — отменить текущее скачивание\n"
            "/terms — условия использования\n"
            "/feedback — написать администратору (пожелание, баг, жалоба)\n"
            "/language — сменить язык интерфейса\n\n"
        ),
        "terms_body": (
            "📄 <b>Условия использования</b>\n\n"
            "1. Бот скачивает видео и Shorts с YouTube по присланной вами "
            "ссылке и отправляет файл в этот чат.\n"
            "2. За соблюдение авторских прав и правил YouTube при "
            "скачивании и дальнейшем использовании видео отвечаете вы. Бот "
            "не хранит скачанные файлы дольше, чем нужно, чтобы отправить "
            "их вам.\n"
            "3. Мы храним минимум данных для работы бота: ваш Telegram-id, "
            "факт и время скачиваний (для дневного лимита и статистики), "
            "id и название скачанных видео (для команды /history). Третьим "
            "лицам эти данные не передаются.\n"
            "4. По запросу правообладателя доступ к скачиванию конкретного "
            "видео может быть закрыт без предупреждения.\n"
            "5. Бот предоставляется «как есть», без гарантий бесперебойной "
            "работы.\n"
            "6. Продолжая пользоваться ботом, вы соглашаетесь с этими "
            "условиями. Мы можем их менять — актуальный текст всегда "
            "доступен по команде /terms.\n\n"
            "{contact_line}"
        ),
        "terms_contact_with": "По вопросам авторских прав или удаления видео: {contact}",
        "terms_contact_without": "По вопросам авторских прав или удаления видео пишите администратору бота.",
        "file_limit_note_local_server": "ℹ️ Максимальный размер файла на этом боте: {mb} МБ.",
        "file_limit_note_default": "⚠️ Ограничение Telegram: боты не могут отправлять файлы крупнее {mb} МБ.",
        "limits_admin_unlimited": "♾️ Вы админ — дневной лимит скачиваний на вас не действует.",
        "limits_db_unavailable": "⚠️ БД сейчас недоступна, лимит проверить не получится.",
        "limits_summary": (
            "📊 Сегодня скачано: {used} из {limit}.\n"
            "Осталось: {remaining}.\n"
            "Лимит обнуляется в полночь по UTC."
        ),
        "history_db_unavailable": "⚠️ БД сейчас недоступна, история недоступна.",
        "history_empty": "Пока нет ни одного скачанного видео.",
        "history_header": "🗂 Последние скачивания (до {limit}):",
        "history_video_fallback_title": "Видео",
        "history_audio_label": "🎵 аудио",
        "feedback_prompt": (
            "✍️ Напишите одним сообщением, что хотите передать "
            "администратору. Подойдёт:\n\n"
            "• пожелание — какую функцию добавить;\n"
            "• проблема или ошибка в работе бота;\n"
            "• жалоба;\n"
            "• видео скачалось неправильно, не воспроизводится или не "
            "скачалось вообще — пришлите ссылку на это видео, чтобы можно "
            "было воспроизвести и исправить проблему.\n\n"
            "Можно приложить скриншот. Следующее сообщение, которое вы "
            "отправите, уйдёт администратору напрямую — если передумали, "
            "отправьте /cancel."
        ),
        "feedback_not_configured": "⚠️ Не удалось отправить — администратор не настроен.",
        "feedback_sent": "✅ Спасибо! Сообщение отправлено администратору.",
        "blocked_video": (
            "🚫 Это видео недоступно для скачивания — доступ закрыт по "
            "запросу правообладателя."
        ),
        "fetching_info": "🔎 Получаю информацию о видео...",
        "live_not_supported": "⚠️ Прямые эфиры пока не поддерживаются.",
        "no_formats": "⚠️ Не удалось найти доступные форматы для этого видео.",
        "video_unavailable": (
            "⚠️ Не получилось получить это видео. Возможно, оно приватное, "
            "удалено или недоступно в регионе, где работает бот."
        ),
        "fetch_error": "⚠️ Что-то пошло не так при получении видео. Попробуйте позже.",
        "choose_resolution": "\nВыберите разрешение или аудио для скачивания:",
        "queue_position": (
            "🕐 В очереди на скачивание — перед вами: {ahead}. Начнём, как "
            "только освободится слот."
        ),
        "downloading_status": "⏳ Скачиваю {target}...",
        "sending_status": "📤 Отправляю {target} в Telegram...",
        "audio_label_short": "аудио",
        "size_limit_exceeded": (
            "⚠️ Файл получился {size} МБ — это больше лимита Telegram для "
            "ботов ({limit} МБ). {note}"
        ),
        "size_limit_note_video": "Обход лимита в разработке — попробуйте разрешение поменьше.",
        "size_limit_note_audio": (
            "Обход лимита в разработке — для этого видео аудио без сжатия "
            "в лимит пока не помещается."
        ),
        "download_cancelled": "❌ Скачивание отменено.",
        "video_unavailable_during_download": "⚠️ Видео стало недоступно во время скачивания.",
        "download_failed": "⚠️ Не удалось скачать видео. Попробуйте ещё раз позже.",
        "link_expired": "Ссылка устарела, отправьте видео ещё раз.",
        "resolution_gone": "Это разрешение больше недоступно.",
        "cancelling_download": "Отменяю скачивание...",
        "feedback_cancelled": "Хорошо, ничего не отправляю администратору.",
        "nothing_to_cancel": "Сейчас нечего отменять.",
        "send_link_prompt": "Пришлите, пожалуйста, ссылку на видео или Shorts с YouTube.",
        "daily_limit_exceeded": (
            "⚠️ Дневной лимит скачиваний исчерпан ({limit} в сутки). "
            "Попробуйте снова после полуночи по UTC."
        ),
        "audio_button": "🎵 Скачать аудио",
        "progress_label_video": "видео",
        "progress_label_audio": "аудио",
        "progress_video_processing": "🔧 Собираю файл {height}p, ещё немного...",
        "progress_video_unknown": "⏳ Скачиваю {height}p ({label})...",
        "progress_video_percent": "⏳ Скачиваю {height}p ({label})\n{bar} {percent}%",
        "progress_audio_processing": "🔧 Собираю файл, ещё немного...",
        "progress_audio_unknown": "⏳ Скачиваю аудио...",
        "progress_audio_percent": "⏳ Скачиваю аудио\n{bar} {percent}%",
        "size_unit_b": "Б",
        "size_unit_kb": "КБ",
        "size_unit_mb": "МБ",
        "size_unit_gb": "ГБ",
        "language_prompt": "🌐 Choose your language / Выберите язык:",
        "language_saved": "✅ Язык переключён на русский.",
    },
    "en": {
        "welcome": (
            "👋 Hi! I download videos and Shorts from YouTube.\n\n"
            "Just send me a video link — I'll show a preview and offer the "
            "available resolutions to download, plus a \"🎵 Download audio\" "
            "button if you only need the sound.\n\n"
            "By downloading a video, you agree to the terms of use — /terms."
        ),
        "help_header": (
            "How to use:\n"
            "1. Send a link to a YouTube video or Shorts.\n"
            "2. Pick a resolution from the buttons — or \"🎵 Download "
            "audio\" if you only need the sound, not the video.\n"
            "3. Wait while I download and send the file.\n\n"
            "Commands:\n"
            "/limits — how many downloads you have left today\n"
            "/history — recently downloaded videos\n"
            "/cancel — cancel the current download\n"
            "/terms — terms of use\n"
            "/feedback — message the administrator (suggestion, bug, complaint)\n"
            "/language — change interface language\n\n"
        ),
        "terms_body": (
            "📄 <b>Terms of Use</b>\n\n"
            "1. The bot downloads YouTube videos and Shorts from the link "
            "you send and delivers the file to this chat.\n"
            "2. You are responsible for complying with copyright law and "
            "YouTube's rules when downloading and using the video. The bot "
            "does not keep downloaded files any longer than needed to send "
            "them to you.\n"
            "3. We store the minimum data needed to run the bot: your "
            "Telegram id, the fact and time of downloads (for the daily "
            "limit and statistics), and the id/title of downloaded videos "
            "(for /history). This data is not shared with third parties.\n"
            "4. Access to downloading a specific video may be revoked "
            "without notice at the copyright holder's request.\n"
            "5. The bot is provided \"as is\", with no guarantee of "
            "uninterrupted operation.\n"
            "6. By continuing to use the bot, you agree to these terms. We "
            "may change them — the current text is always available via "
            "/terms.\n\n"
            "{contact_line}"
        ),
        "terms_contact_with": "For copyright or takedown requests: {contact}",
        "terms_contact_without": "For copyright or takedown requests, please contact the bot administrator.",
        "file_limit_note_local_server": "ℹ️ Maximum file size on this bot: {mb} MB.",
        "file_limit_note_default": "⚠️ Telegram limit: bots can't send files larger than {mb} MB.",
        "limits_admin_unlimited": "♾️ You're an admin — the daily download limit doesn't apply to you.",
        "limits_db_unavailable": "⚠️ The database is unavailable right now, so I can't check your limit.",
        "limits_summary": (
            "📊 Downloaded today: {used} of {limit}.\n"
            "Remaining: {remaining}.\n"
            "The limit resets at midnight UTC."
        ),
        "history_db_unavailable": "⚠️ The database is unavailable right now, history isn't available.",
        "history_empty": "No downloads yet.",
        "history_header": "🗂 Recent downloads (up to {limit}):",
        "history_video_fallback_title": "Video",
        "history_audio_label": "🎵 audio",
        "feedback_prompt": (
            "✍️ Write in one message what you'd like to tell the "
            "administrator. For example:\n\n"
            "• a suggestion — what feature to add;\n"
            "• a problem or bug in how the bot works;\n"
            "• a complaint;\n"
            "• a video that downloaded incorrectly, won't play, or didn't "
            "download at all — please include a link to it so the issue "
            "can be reproduced and fixed.\n\n"
            "You can attach a screenshot. The next message you send will "
            "go straight to the administrator — if you changed your mind, "
            "send /cancel."
        ),
        "feedback_not_configured": "⚠️ Couldn't send — no administrator is configured.",
        "feedback_sent": "✅ Thanks! Your message has been sent to the administrator.",
        "blocked_video": (
            "🚫 This video isn't available for download — access was "
            "revoked at the copyright holder's request."
        ),
        "fetching_info": "🔎 Fetching video info...",
        "live_not_supported": "⚠️ Live streams aren't supported yet.",
        "no_formats": "⚠️ Couldn't find any available formats for this video.",
        "video_unavailable": (
            "⚠️ Couldn't fetch this video. It might be private, deleted, "
            "or unavailable in the region where the bot runs."
        ),
        "fetch_error": "⚠️ Something went wrong while fetching the video. Please try again later.",
        "choose_resolution": "\nChoose a resolution or audio to download:",
        "queue_position": (
            "🕐 In the download queue — ahead of you: {ahead}. We'll start "
            "as soon as a slot frees up."
        ),
        "downloading_status": "⏳ Downloading {target}...",
        "sending_status": "📤 Sending {target} to Telegram...",
        "audio_label_short": "audio",
        "size_limit_exceeded": (
            "⚠️ The file turned out to be {size} MB — that's over "
            "Telegram's bot limit ({limit} MB). {note}"
        ),
        "size_limit_note_video": "A workaround is in development — try a lower resolution.",
        "size_limit_note_audio": (
            "A workaround is in development — for this video, the "
            "uncompressed audio doesn't fit the limit yet."
        ),
        "download_cancelled": "❌ Download cancelled.",
        "video_unavailable_during_download": "⚠️ The video became unavailable during the download.",
        "download_failed": "⚠️ Couldn't download the video. Please try again later.",
        "link_expired": "This link has expired, please send the video again.",
        "resolution_gone": "This resolution is no longer available.",
        "cancelling_download": "Cancelling the download...",
        "feedback_cancelled": "OK, nothing will be sent to the administrator.",
        "nothing_to_cancel": "There's nothing to cancel right now.",
        "send_link_prompt": "Please send a link to a YouTube video or Shorts.",
        "daily_limit_exceeded": (
            "⚠️ Daily download limit reached ({limit} per day). Try again "
            "after midnight UTC."
        ),
        "audio_button": "🎵 Download audio",
        "progress_label_video": "video",
        "progress_label_audio": "audio",
        "progress_video_processing": "🔧 Putting the file together {height}p, almost done...",
        "progress_video_unknown": "⏳ Downloading {height}p ({label})...",
        "progress_video_percent": "⏳ Downloading {height}p ({label})\n{bar} {percent}%",
        "progress_audio_processing": "🔧 Putting the file together, almost done...",
        "progress_audio_unknown": "⏳ Downloading audio...",
        "progress_audio_percent": "⏳ Downloading audio\n{bar} {percent}%",
        "size_unit_b": "B",
        "size_unit_kb": "KB",
        "size_unit_mb": "MB",
        "size_unit_gb": "GB",
        "language_prompt": "🌐 Choose your language / Выберите язык:",
        "language_saved": "✅ Language switched to English.",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Достать перевод по ключу и языку, с фолбэком на DEFAULT_LANGUAGE, а
    если ключа и там нет — вернуть сам ключ (заметно в чате, что что-то не
    перевели, вместо KeyError, роняющего обработчик)."""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANGUAGE]
    text = table.get(key)
    if text is None:
        text = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    return text.format(**kwargs) if kwargs else text


def resolve_language(telegram_language_code: str | None, ui_language: str | None) -> str:
    """Эффективный язык интерфейса для пользователя.

    Приоритет: явный выбор через /language (User.ui_language) > язык
    клиента Telegram (User.language_code/update.from_user.language_code,
    только "ru" распознаём отдельно, всё остальное — DEFAULT_LANGUAGE) >
    DEFAULT_LANGUAGE, если вообще ничего не известно.
    """
    if ui_language in SUPPORTED_LANGUAGES:
        return ui_language
    if telegram_language_code and telegram_language_code.lower().startswith("ru"):
        return "ru"
    return DEFAULT_LANGUAGE
