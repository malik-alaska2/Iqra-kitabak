"""Переводы интерфейса: uz / ru / ar."""

LANGS = {"uz": "🇺🇿 O‘zbekcha", "ru": "🇷🇺 Русский", "ar": "🇸🇦 العربية"}
DEFAULT_LANG = "ru"

TEXTS = {
    # ------------------------------------------------------------------ uz --
    "uz": {
        "choose_lang": "Tilni tanlang:",
        "lang_saved": "Til o‘zgartirildi ✅",
        "start": (
            "<b>Kitob</b> — islomiy va boshqa kitoblar kutubxonasi.\n\n"
            "Kitob nomini yoki muallifni yozing — men ochiq manbalardan "
            "eng yaxshi nusxalarni topaman va PDF / EPUB / TXT ko‘rinishida yuboraman.\n"
            "Yuklab olingan kitoblar internetsiz ham ochiladi."
        ),
        "menu_search": "🔎 Qidiruv",
        "menu_fav": "⭐ Saralangan",
        "menu_lib": "📥 Mening kitoblarim",
        "menu_app": "📱 Ilova",
        "menu_lang": "🌐 Til",
        "menu_help": "❓ Yordam",
        "search_prompt": "Kitob nomini yoki muallifni yozing:",
        "searching": "🔎 Qidirilmoqda…",
        "no_results": "Hech narsa topilmadi. Nomni boshqacha yozib ko‘ring yoki muallif ismini kiriting.",
        "results": "Topildi: <b>{n}</b> ta. Raqamni tanlang:",
        "page": "Sahifa {cur}/{total}",
        "prev": "◀️ Orqaga",
        "next": "Keyingi ▶️",
        "back_to_list": "↩️ Ro‘yxatga",
        "formats": "Yuklab olish formatini tanlang:",
        "author": "Muallif",
        "year": "Yil",
        "source": "Manba",
        "size": "Hajm",
        "downloading": "⏳ Yuklanmoqda…",
        "sent": "✅ Tayyor. Fayl chatda saqlanadi — internetsiz ham ochiladi.",
        "too_big": "Fayl juda katta ({size}). Havola orqali yuklab oling:",
        "dl_error": "Yuklab bo‘lmadi. Havolani sinab ko‘ring:",
        "fav_added": "⭐ Saralanganlarga qo‘shildi",
        "fav_removed": "Saralanganlardan olib tashlandi",
        "fav_add_btn": "⭐ Saralanganga",
        "fav_del_btn": "🗑 O‘chirish",
        "fav_empty": "Saralanganlar bo‘sh. Kitob kartasida ⭐ tugmasini bosing.",
        "fav_title": "⭐ <b>Saralangan kitoblar</b>",
        "lib_empty": "Siz hali kitob yuklamagansiz.",
        "lib_title": "📥 <b>Mening kitoblarim</b> — bosing, fayl qayta yuboriladi:",
        "open_app": "📱 Ilovani ochish",
        "open_link": "🌐 Havola",
        "help": (
            "<b>Qanday ishlaydi</b>\n"
            "• Kitob nomini yozing — natijalar ro‘yxati chiqadi.\n"
            "• Raqamni bosing — format va hajmni tanlaysiz.\n"
            "• ⭐ — saralanganga saqlash.\n"
            "• 📥 «Mening kitoblarim» — yuklangan kitoblar tarixi.\n"
            "• 📱 Ilova — qulay o‘qish, offline kutubxona.\n\n"
            "Buyruqlar: /start /search /favorites /library /lang /help"
        ),
        "presets": "Yoki bo‘limni tanlang:",
        "topics": {
            "quran": "📖 Qur'on va tafsir",
            "hadith": "📜 Hadis",
            "fiqh": "⚖️ Fiqh",
            "aqidah": "🕌 Aqida",
            "seerah": "🌙 Siyra va tarix",
        },
    },
    # ------------------------------------------------------------------ ru --
    "ru": {
        "choose_lang": "Выберите язык:",
        "lang_saved": "Язык изменён ✅",
        "start": (
            "<b>Kitob</b> — библиотека исламских и других книг.\n\n"
            "Напишите название книги или автора — найду лучшие копии в открытых "
            "источниках и пришлю в PDF / EPUB / TXT.\n"
            "Скачанные книги открываются без интернета."
        ),
        "menu_search": "🔎 Поиск",
        "menu_fav": "⭐ Избранное",
        "menu_lib": "📥 Мои книги",
        "menu_app": "📱 Приложение",
        "menu_lang": "🌐 Язык",
        "menu_help": "❓ Помощь",
        "search_prompt": "Напишите название книги или автора:",
        "searching": "🔎 Ищу…",
        "no_results": "Ничего не нашёл. Попробуйте другое написание или имя автора.",
        "results": "Найдено: <b>{n}</b>. Выберите номер:",
        "page": "Стр. {cur}/{total}",
        "prev": "◀️ Назад",
        "next": "Далее ▶️",
        "back_to_list": "↩️ К списку",
        "formats": "Выберите формат для скачивания:",
        "author": "Автор",
        "year": "Год",
        "source": "Источник",
        "size": "Размер",
        "downloading": "⏳ Загружаю…",
        "sent": "✅ Готово. Файл остаётся в чате — открывается без интернета.",
        "too_big": "Файл слишком большой ({size}). Скачайте по ссылке:",
        "dl_error": "Не удалось загрузить. Попробуйте ссылку:",
        "fav_added": "⭐ Добавлено в избранное",
        "fav_removed": "Удалено из избранного",
        "fav_add_btn": "⭐ В избранное",
        "fav_del_btn": "🗑 Удалить",
        "fav_empty": "Избранное пусто. Нажмите ⭐ в карточке книги.",
        "fav_title": "⭐ <b>Избранные книги</b>",
        "lib_empty": "Вы ещё ничего не скачивали.",
        "lib_title": "📥 <b>Мои книги</b> — нажмите, чтобы получить файл снова:",
        "open_app": "📱 Открыть приложение",
        "open_link": "🌐 Ссылка",
        "help": (
            "<b>Как это работает</b>\n"
            "• Напишите название — получите список результатов.\n"
            "• Нажмите номер — выберете формат и размер.\n"
            "• ⭐ — сохранить в избранное.\n"
            "• 📥 «Мои книги» — история скачанных книг.\n"
            "• 📱 Приложение — удобное чтение и офлайн-библиотека.\n\n"
            "Команды: /start /search /favorites /library /lang /help"
        ),
        "presets": "Или выберите раздел:",
        "topics": {
            "quran": "📖 Коран и тафсир",
            "hadith": "📜 Хадисы",
            "fiqh": "⚖️ Фикх",
            "aqidah": "🕌 Акыда",
            "seerah": "🌙 Сира и история",
        },
    },
    # ------------------------------------------------------------------ ar --
    "ar": {
        "choose_lang": "اختر اللغة:",
        "lang_saved": "تم تغيير اللغة ✅",
        "start": (
            "<b>كتاب</b> — مكتبة الكتب الإسلامية وغيرها.\n\n"
            "اكتب اسم الكتاب أو المؤلف، وسأبحث عن أفضل النسخ في المصادر المفتوحة "
            "وأرسلها بصيغة PDF / EPUB / TXT.\n"
            "الكتب المحمّلة تُفتح بدون إنترنت."
        ),
        "menu_search": "🔎 بحث",
        "menu_fav": "⭐ المفضلة",
        "menu_lib": "📥 كتبي",
        "menu_app": "📱 التطبيق",
        "menu_lang": "🌐 اللغة",
        "menu_help": "❓ مساعدة",
        "search_prompt": "اكتب اسم الكتاب أو المؤلف:",
        "searching": "🔎 جارٍ البحث…",
        "no_results": "لم أجد شيئًا. جرّب كتابة الاسم بشكل آخر أو اسم المؤلف.",
        "results": "النتائج: <b>{n}</b>. اختر الرقم:",
        "page": "صفحة {cur}/{total}",
        "prev": "◀️ السابق",
        "next": "التالي ▶️",
        "back_to_list": "↩️ إلى القائمة",
        "formats": "اختر صيغة التحميل:",
        "author": "المؤلف",
        "year": "السنة",
        "source": "المصدر",
        "size": "الحجم",
        "downloading": "⏳ جارٍ التحميل…",
        "sent": "✅ تم. الملف يبقى في المحادثة ويُفتح بدون إنترنت.",
        "too_big": "الملف كبير جدًا ({size}). حمّله عبر الرابط:",
        "dl_error": "تعذّر التحميل. جرّب الرابط:",
        "fav_added": "⭐ أُضيف إلى المفضلة",
        "fav_removed": "أُزيل من المفضلة",
        "fav_add_btn": "⭐ إلى المفضلة",
        "fav_del_btn": "🗑 حذف",
        "fav_empty": "المفضلة فارغة. اضغط ⭐ في بطاقة الكتاب.",
        "fav_title": "⭐ <b>الكتب المفضلة</b>",
        "lib_empty": "لم تحمّل أي كتاب بعد.",
        "lib_title": "📥 <b>كتبي</b> — اضغط لإعادة إرسال الملف:",
        "open_app": "📱 فتح التطبيق",
        "open_link": "🌐 رابط",
        "help": (
            "<b>طريقة الاستخدام</b>\n"
            "• اكتب اسم الكتاب لتظهر قائمة النتائج.\n"
            "• اضغط الرقم لاختيار الصيغة والحجم.\n"
            "• ⭐ للحفظ في المفضلة.\n"
            "• 📥 «كتبي» — سجل الكتب المحمّلة.\n"
            "• 📱 التطبيق — قراءة مريحة ومكتبة بدون إنترنت.\n\n"
            "الأوامر: /start /search /favorites /library /lang /help"
        ),
        "presets": "أو اختر قسمًا:",
        "topics": {
            "quran": "📖 القرآن والتفسير",
            "hadith": "📜 الحديث",
            "fiqh": "⚖️ الفقه",
            "aqidah": "🕌 العقيدة",
            "seerah": "🌙 السيرة والتاريخ",
        },
    },
}

# Поисковые запросы для кнопок-разделов (не переводятся — идут в источники как есть)
TOPIC_QUERIES = {
    "quran": {"ru": "тафсир Коран", "uz": "Qur'on tafsir", "ar": "تفسير القرآن"},
    "hadith": {"ru": "хадисы сборник", "uz": "hadis to'plami", "ar": "صحيح الحديث"},
    "fiqh": {"ru": "фикх исламское право", "uz": "fiqh islom huquqi", "ar": "الفقه الإسلامي"},
    "aqidah": {"ru": "акыда вероубеждение ислам", "uz": "aqida islom", "ar": "العقيدة الإسلامية"},
    "seerah": {"ru": "сира пророк Мухаммад история", "uz": "siyra payg'ambar tarixi", "ar": "السيرة النبوية"},
}


def t(lang: str, key: str, **kwargs) -> str:
    """Вернуть строку перевода; при отсутствии — русский вариант."""
    data = TEXTS.get(lang) or TEXTS[DEFAULT_LANG]
    value = data.get(key) or TEXTS[DEFAULT_LANG].get(key, key)
    if isinstance(value, str) and kwargs:
        return value.format(**kwargs)
    return value


def topic_title(lang: str, key: str) -> str:
    return t(lang, "topics").get(key, key)


def menu_labels() -> dict:
    """Соответствие «текст кнопки» -> «действие» для всех языков сразу."""
    mapping = {}
    for lang, data in TEXTS.items():
        for action in ("search", "fav", "lib", "app", "lang", "help"):
            mapping[data[f"menu_{action}"]] = action
    return mapping
