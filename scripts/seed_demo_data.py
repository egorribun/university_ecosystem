"""
Seed script — creates demo data after a fresh Docker install.

Usage:
    python scripts/seed_demo_data.py

Requires the Docker stack to be running (PostgreSQL reachable).
Safe to re-run: each section skips silently on unique-constraint violations.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

# When running from the host machine (outside Docker) the DATABASE_URL in .env
# uses the Docker-internal hostname "postgres" which doesn't resolve on the host.
# Replace it with "localhost" ONLY when we had to load .env (i.e. we're on the host).
_loaded_from_dotenv = False
if "DATABASE_URL" not in os.environ:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        _loaded_from_dotenv = True
    except ImportError:
        pass

if _loaded_from_dotenv:
    _db_url = os.environ.get("DATABASE_URL", "")
    if "@postgres:" in _db_url:
        os.environ["DATABASE_URL"] = _db_url.replace("@postgres:", "@localhost:")

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.security import get_password_hash_sync  # noqa: E402
from app.core.database import async_session, init_database  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.events import Event  # noqa: E402
from app.models.news import News  # noqa: E402
from app.models.schedule import Group, Schedule  # noqa: E402
from app.models.stories import Story  # noqa: E402
from app.models.users import EducationPath, User, UserProfile  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# Reference Monday for schedule time columns (any consistent week works)
_MON = _dt(2026, 1, 5)
_TUE = _dt(2026, 1, 6)
_WED = _dt(2026, 1, 7)
_THU = _dt(2026, 1, 8)
_FRI = _dt(2026, 1, 9)


def _pair(base: datetime, pair: int) -> tuple[datetime, datetime]:
    """Return (start, end) for Russian university pair number 1-5."""
    slots = [
        (9, 0, 10, 30),
        (10, 40, 12, 10),
        (12, 20, 13, 50),
        (14, 0, 15, 30),
        (15, 40, 17, 10),
    ]
    sh, sm, eh, em = slots[pair - 1]
    return (
        base.replace(hour=sh, minute=sm),
        base.replace(hour=eh, minute=em),
    )


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

NEWS_DATA = [
    {
        "title": "ГУУ вошёл в топ-20 лучших университетов страны",
        "content": (
            "## Итоги рейтинга\n\n"
            "По результатам ежегодного национального рейтинга Государственный "
            "университет управления занял **18-е место** среди ведущих вузов России. "
            "Особую роль сыграли достижения в области цифровизации образования, "
            "научных публикаций и уровня трудоустройства выпускников.\n\n"
            "## Ключевые показатели\n\n"
            "| Показатель | Значение | Изменение |\n"
            "|---|---|---|\n"
            "| Общий балл | 87.4 | +3.2 |\n"
            "| Трудоустройство | 92% | +5% |\n"
            "| Публикации (Scopus) | 340 | +48 |\n"
            "| Цифровизация | 9.1/10 | +0.8 |\n\n"
            "## Что это значит для студентов\n\n"
            "Рост в рейтинге напрямую влияет на:\n\n"
            "- **Стоимость диплома** — работодатели ценят выпускников топ-20 вузов\n"
            "- **Международные обмены** — новые партнёрства с зарубежными университетами\n"
            "- **Финансирование** — больше грантов и стипендий для исследований\n\n"
            "> Ректор университета поблагодарил преподавателей и студентов за "
            "совместный труд и пообещал продолжить развитие инфраструктуры.\n\n"
            "### Методология\n\n"
            "Рейтинг составляется по методике [RAEX](https://raex-rr.com), "
            "учитывающей *качество образования*, *научную деятельность* и "
            "*востребованность выпускников*. Данные собираются из открытых "
            "источников и внутренней отчётности вузов.\n\n"
            "---\n\n"
            "Подробные результаты и сравнительные таблицы доступны на сайте "
            "рейтингового агентства."
        ),
        "image_url": "https://picsum.photos/seed/news1/800/600",
    },
    {
        "title": "Открыт приём заявок на международную конференцию по ИИ",
        "content": (
            "Кафедра информационных технологий объявляет о приёме научных докладов "
            "на XVI Международную конференцию «Интеллектуальные системы и технологии». "
            "Дедлайн подачи тезисов — 15 мая 2026 года. Лучшие работы будут "
            "опубликованы в сборнике, индексируемом в Scopus. "
            "Участие бесплатное для студентов и аспирантов университета."
        ),
        "image_url": "https://picsum.photos/seed/news2/800/600",
    },
    {
        "title": "Студенты ГУУ победили на хакатоне FinTech Challenge 2026",
        "content": (
            "Команда «Байт и код» из Института информационных технологий заняла "
            "первое место на всероссийском хакатоне по финансовым технологиям. "
            "За 48 часов ребята разработали систему автоматического скоринга заёмщиков "
            "на основе машинного обучения. Призовой фонд составил 300 000 рублей, "
            "а победители получили предложения о стажировке от трёх крупных банков."
        ),
        "image_url": "https://picsum.photos/seed/news3/800/600",
    },
    {
        "title": "Новая лаборатория робототехники открылась в корпусе А",
        "content": (
            "В рамках федеральной программы «Приоритет-2030» в университете открылась "
            "современная лаборатория робототехники и промышленной автоматизации. "
            "Оснащение включает шесть промышленных манипуляторов, систему машинного "
            "зрения и стенды для отработки алгоритмов управления. Лаборатория "
            "доступна студентам с 3-го курса специальности «Мехатроника и робототехника»."
        ),
        "image_url": "https://picsum.photos/seed/news4/800/600",
    },
    {
        "title": "День открытых дверей пройдёт 12 апреля",
        "content": (
            "Приглашаем абитуриентов и их родителей на традиционный День открытых дверей. "
            "Гости смогут посетить экскурсии по кампусу, познакомиться с деканами "
            "факультетов, задать вопросы приёмной комиссии и поучаствовать в "
            "демонстрационных мастер-классах. Регистрация открыта на сайте университета."
        ),
        "image_url": "https://picsum.photos/seed/news5/800/600",
    },
    {
        "title": "Стипендии имени Сеченова для студентов-медиков",
        "content": (
            "Объявлен конкурс на именные стипендии фонда «Медицина будущего» для "
            "студентов медицинских направлений. Размер ежемесячной выплаты — 25 000 руб. "
            "Необходимые документы: академическое портфолио, рекомендательное письмо "
            "научного руководителя и эссе о карьерных целях. Дедлайн — 30 апреля."
        ),
        "image_url": "https://picsum.photos/seed/news6/800/600",
    },
    {
        "title": "Весенний спортивный фестиваль «Здоровый кампус»",
        "content": (
            "С 19 по 25 апреля пройдёт традиционный весенний спортивный марафон. "
            "В программе: турниры по мини-футболу, волейболу, баскетболу и настольному "
            "теннису, а также забег «5 км за ГУУ» на набережной. Победители получат "
            "сертификаты в спортивный магазин. Регистрация команд до 16 апреля."
        ),
        "image_url": "https://picsum.photos/seed/news7/800/600",
    },
    {
        "title": "Соглашение о сотрудничестве с «Яндекс Образованием»",
        "content": (
            "Университет подписал трёхлетнее соглашение с «Яндекс Образованием» о "
            "совместных образовательных программах. В рамках партнёрства студенты ИТ-"
            "направлений получат доступ к платформе Practicum и возможность прохождения "
            "оплачиваемой стажировки в командах Яндекса. Первые места доступны уже в "
            "летнем наборе 2026 года."
        ),
        "image_url": "https://picsum.photos/seed/news8/800/600",
    },
    {
        "title": "Конкурс студенческих стартапов — подайте заявку до 5 мая",
        "content": (
            "Студенческий бизнес-акселератор ГУУ принимает заявки на конкурс стартапов "
            "«Цифровой прорыв». Проекты оцениваются по четырём трекам: EdTech, HealthTech, "
            "GreenTech и FinTech. Победители получат финансирование до 500 000 рублей "
            "и место в коворкинге технопарка сроком на один год."
        ),
        "image_url": "https://picsum.photos/seed/news9/800/600",
    },
    {
        "title": "Новый курс «Этика ИИ» открылся для всех направлений",
        "content": (
            "С осеннего семестра 2026 года факультативный курс «Этика искусственного "
            "интеллекта и цифровые права» будет доступен студентам всех специальностей. "
            "Лекции будет читать приглашённый профессор из НИУ ВШЭ. Запись открыта в "
            "личном кабинете студента. Количество мест ограничено — 120 человек."
        ),
        "image_url": "https://picsum.photos/seed/news10/800/600",
    },
]

STORIES_DATA = [
    {
        "title": "🎓 Сессия: советы по подготовке",
        "short_text": "Как сдать сессию на отлично: 7 проверенных способов от старших курсов.",
        "cover_url": "https://picsum.photos/seed/story1/400/700",
    },
    {
        "title": "📢 Открытая лекция: Web 3.0",
        "short_text": "Завтра в 18:00 аудитория 301 — лекция об архитектуре децентрализованных приложений.",
        "cover_url": "https://picsum.photos/seed/story2/400/700",
    },
    {
        "title": "🏆 Наши победили!",
        "short_text": "Команда ГУУ заняла 1-е место на региональном чемпионате по программированию.",
        "cover_url": "https://picsum.photos/seed/story3/400/700",
    },
    {
        "title": "☕ Новая кофейня в корпусе Б",
        "short_text": "Открылась студенческая кофейня с завтраками от 99 рублей. Работает с 8:00.",
        "cover_url": "https://picsum.photos/seed/story4/400/700",
    },
    {
        "title": "📚 Библиотека обновила каталог",
        "short_text": "Поступило 200+ новых книг по программированию, Data Science и кибербезопасности.",
        "cover_url": "https://picsum.photos/seed/story5/400/700",
    },
    {
        "title": "🎸 Репетиция студ. группы",
        "short_text": "Студенческая рок-группа «Нулевой указатель» ищет барабанщика. Проба сил в пт 17:00.",
        "cover_url": "https://picsum.photos/seed/story6/400/700",
    },
    {
        "title": "🌱 Субботник в кампусе",
        "short_text": "Присоединяйся к весеннему субботнику в эту субботу. Начало в 10:00, корпус А.",
        "cover_url": "https://picsum.photos/seed/story7/400/700",
    },
    {
        "title": "💼 Ярмарка вакансий",
        "short_text": "15 апреля — день карьеры. 40+ компаний ищут стажёров и выпускников.",
        "cover_url": "https://picsum.photos/seed/story8/400/700",
    },
    {
        "title": "🔬 День науки в ГУУ",
        "short_text": "Выставка научных проектов студентов. Голосуй за лучший — призы от партнёров.",
        "cover_url": "https://picsum.photos/seed/story9/400/700",
    },
    {
        "title": "🍕 Пицца-вечер факультета",
        "short_text": "Пятница, 19:00, холл ИИТ — неформальная встреча потока с преподавателями.",
        "cover_url": "https://picsum.photos/seed/story10/400/700",
    },
    {
        "title": "📱 Обновление мобильного приложения",
        "short_text": "Вышла версия 2.5 приложения ГУУ: push-уведомления о парах и новый чат группы.",
        "cover_url": "https://picsum.photos/seed/story11/400/700",
    },
    {
        "title": "🎨 Выставка студенческих работ",
        "short_text": "В галерее корпуса В открылась выставка дизайн-проектов 4-го курса.",
        "cover_url": "https://picsum.photos/seed/story12/400/700",
    },
    {
        "title": "🏋️ Тренажёрный зал",
        "short_text": "Запишись на секцию по единоборствам — набор до 20 апреля, спорт. корпус 2 этаж.",
        "cover_url": "https://picsum.photos/seed/story13/400/700",
    },
    {
        "title": "🚀 Митап: стартапы и карьера в IT",
        "short_text": "Выпускники расскажут о своём пути от первокурсника до CTO. Среда 18:30.",
        "cover_url": "https://picsum.photos/seed/story14/400/700",
    },
    {
        "title": "🌍 Программа обмена 2026–27",
        "short_text": "Открыт приём заявок на академический обмен с университетами Германии и Финляндии.",
        "cover_url": "https://picsum.photos/seed/story15/400/700",
    },
]

EVENTS_DATA = [
    {
        "title": "Открытая лекция: «Будущее ИИ в образовании»",
        "description": "Профессор МГУ Андрей Волков расскажет о применении генеративных моделей в педагогике, автоматической проверке заданий и персонализированных траекториях обучения.",
        "location": "Актовый зал, корпус А, ГУУ",
        "event_type": "lecture",
        "starts_at": _dt(2026, 4, 10, 15, 0),
        "ends_at": _dt(2026, 4, 10, 17, 0),
        "image_url": "https://picsum.photos/seed/event1/800/600",
    },
    {
        "title": "Воркшоп «FastAPI: от нуля до продакшена»",
        "description": "Практический однодневный воркшоп по построению REST-API на Python. Участники разработают полноценный микросервис с авторизацией, тестами и Docker-сборкой.",
        "location": "Лаб. 204, корпус Б",
        "event_type": "workshop",
        "starts_at": _dt(2026, 4, 15, 10, 0),
        "ends_at": _dt(2026, 4, 15, 18, 0),
        "image_url": "https://picsum.photos/seed/event2/800/600",
    },
    {
        "title": "Олимпиада по алгоритмическому программированию",
        "description": "Открытая студенческая олимпиада для команд из 2–3 человек. Платформа Codeforces, 5 часов, 10 задач разного уровня сложности. Призовой фонд 120 000 руб.",
        "location": "Компьютерный класс 315, корпус Г",
        "event_type": "competition",
        "starts_at": _dt(2026, 4, 20, 9, 0),
        "ends_at": _dt(2026, 4, 20, 14, 0),
        "image_url": "https://picsum.photos/seed/event3/800/600",
    },
    {
        "title": "Весенний концерт студенческих творческих коллективов",
        "description": "Ежегодный весенний концерт с участием хора ГУУ, студенческого театра, танцевальных и вокальных коллективов. Вход свободный по студенческому билету.",
        "location": "Большой актовый зал",
        "event_type": "cultural",
        "starts_at": _dt(2026, 4, 25, 18, 30),
        "ends_at": _dt(2026, 4, 25, 21, 0),
        "image_url": "https://picsum.photos/seed/event4/800/600",
    },
    {
        "title": "Ярмарка вакансий «Карьера в IT»",
        "description": "Более 40 компаний-партнёров, включая Яндекс, Сбер, VK и Тинькофф, представят стажировки и вакансии для студентов и выпускников IT-направлений.",
        "location": "Большой актовый зал + фойе корпуса А",
        "event_type": "workshop",
        "starts_at": _dt(2026, 5, 6, 11, 0),
        "ends_at": _dt(2026, 5, 6, 17, 0),
        "image_url": "https://picsum.photos/seed/event5/800/600",
    },
    {
        "title": "Хакатон «Цифровой университет»",
        "description": "48-часовой хакатон по разработке цифровых сервисов для университетской экосистемы. Трекеры: расписание, уведомления, аналитика успеваемости. Призы от партнёров.",
        "location": "Коворкинг ГУУ Tech Hub, корпус В",
        "event_type": "competition",
        "starts_at": _dt(2026, 5, 16, 10, 0),
        "ends_at": _dt(2026, 5, 18, 10, 0),
        "image_url": "https://picsum.photos/seed/event6/800/600",
    },
    {
        "title": "Мастер-класс: публичные выступления и питчинг",
        "description": "Тренер по риторике Елена Смирнова проведёт практический мастер-класс по структуре питча стартапа, работе с голосом и жестами перед инвесторской аудиторией.",
        "location": "Аудитория 118, корпус А",
        "event_type": "workshop",
        "starts_at": _dt(2026, 5, 22, 14, 0),
        "ends_at": _dt(2026, 5, 22, 17, 0),
        "image_url": "https://picsum.photos/seed/event7/800/600",
    },
    {
        "title": "Первенство ГУУ по мини-футболу",
        "description": "Межфакультетский турнир по мини-футболу в формате плей-офф. Заявки принимаются командами по 8 человек. Матчи проходят в выходные дни в течение всего мая.",
        "location": "Спортивный комплекс ГУУ, поле 1",
        "event_type": "sports",
        "starts_at": _dt(2026, 5, 30, 10, 0),
        "ends_at": _dt(2026, 5, 30, 18, 0),
        "image_url": "https://picsum.photos/seed/event8/800/600",
    },
    {
        "title": "Защита дипломных проектов — ИИТ 2026",
        "description": "Открытая публичная защита выпускных квалификационных работ студентов Института информационных технологий. Все желающие могут присутствовать и задавать вопросы.",
        "location": "Конференц-зал, корпус Б, 3 этаж",
        "event_type": "lecture",
        "starts_at": _dt(2026, 6, 10, 9, 0),
        "ends_at": _dt(2026, 6, 10, 18, 0),
        "image_url": "https://picsum.photos/seed/event9/800/600",
    },
    {
        "title": "Выпускной вечер 2026",
        "description": "Торжественная церемония вручения дипломов выпускникам 2026 года. Программа включает поздравления от ректора, вручение почётных грамот и банкет.",
        "location": "Центральный актовый зал ГУУ",
        "event_type": "cultural",
        "starts_at": _dt(2026, 6, 28, 17, 0),
        "ends_at": _dt(2026, 6, 28, 23, 0),
        "image_url": "https://picsum.photos/seed/event10/800/600",
    },
]

# (weekday, pair_number, subject, teacher, room, lesson_type, parity)
SCHEDULE_DATA = [
    # ── Monday ───────────────────────────────────────────────────
    ("monday", 1, "Математический анализ", "Иванов А.В.", "А-101", "lecture", "both"),
    (
        "monday",
        2,
        "Программирование на Python",
        "Петров И.С.",
        "Б-204",
        "practice",
        "odd",
    ),
    ("monday", 3, "Линейная алгебра", "Соколова Н.П.", "А-105", "lecture", "even"),
    ("monday", 4, "Базы данных", "Кузнецов Д.Р.", "Б-310", "practice", "odd"),
    ("monday", 4, "Операционные системы", "Волков К.Е.", "В-112", "practice", "even"),
    # ── Tuesday ──────────────────────────────────────────────────
    (
        "tuesday",
        1,
        "Алгоритмы и структуры данных",
        "Новиков Р.М.",
        "Б-201",
        "lecture",
        "both",
    ),
    ("tuesday", 2, "Веб-разработка", "Орлова Т.В.", "Б-315", "practice", "odd"),
    ("tuesday", 3, "Компьютерные сети", "Морозов С.Г.", "А-203", "lecture", "even"),
    (
        "tuesday",
        3,
        "Иностранный язык (Английский)",
        "Смирнова Е.Л.",
        "А-408",
        "practice",
        "odd",
    ),
    (
        "tuesday",
        4,
        "Иностранный язык (Английский)",
        "Смирнова Е.Л.",
        "А-408",
        "practice",
        "even",
    ),
    # ── Wednesday ────────────────────────────────────────────────
    (
        "wednesday",
        1,
        "Математический анализ",
        "Иванов А.В.",
        "А-101",
        "practice",
        "odd",
    ),
    ("wednesday", 1, "Линейная алгебра", "Соколова Н.П.", "А-105", "practice", "even"),
    ("wednesday", 2, "Базы данных", "Кузнецов Д.Р.", "Б-310", "lecture", "both"),
    ("wednesday", 3, "Защита информации", "Лебедев П.А.", "В-215", "lecture", "odd"),
    ("wednesday", 3, "Экономика", "Козлова М.И.", "А-302", "lecture", "even"),
    (
        "wednesday",
        5,
        "Физическая культура",
        "Тихонов В.В.",
        "Спорт. зал",
        "practice",
        "both",
    ),
    # ── Thursday ─────────────────────────────────────────────────
    (
        "thursday",
        1,
        "Программирование на Python",
        "Петров И.С.",
        "Б-204",
        "lecture",
        "both",
    ),
    ("thursday", 2, "Операционные системы", "Волков К.Е.", "В-112", "lecture", "odd"),
    ("thursday", 2, "Защита информации", "Лебедев П.А.", "В-215", "practice", "even"),
    ("thursday", 3, "Веб-разработка", "Орлова Т.В.", "Б-315", "lecture", "even"),
    (
        "thursday",
        3,
        "Алгоритмы и структуры данных",
        "Новиков Р.М.",
        "Б-201",
        "practice",
        "odd",
    ),
    ("thursday", 4, "Экономика", "Козлова М.И.", "А-302", "practice", "odd"),
    # ── Friday ───────────────────────────────────────────────────
    ("friday", 1, "Компьютерные сети", "Морозов С.Г.", "А-203", "practice", "odd"),
    (
        "friday",
        1,
        "Программирование на Python",
        "Петров И.С.",
        "Б-204",
        "practice",
        "even",
    ),
    ("friday", 2, "Философия", "Беляева Г.Н.", "А-501", "lecture", "both"),
    (
        "friday",
        3,
        "Иностранный язык (Английский)",
        "Смирнова Е.Л.",
        "А-409",
        "practice",
        "both",
    ),
    ("friday", 4, "Защита информации", "Лебедев П.А.", "В-215", "lecture", "even"),
    ("friday", 4, "Компьютерные сети", "Морозов С.Г.", "А-203", "lecture", "even"),
]

_DAY_BASE = {
    "monday": _MON,
    "tuesday": _TUE,
    "wednesday": _WED,
    "thursday": _THU,
    "friday": _FRI,
}


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------


async def seed_group(db) -> Group:
    group = Group(name="ЗИ-301", course=3, faculty="Институт информационных технологий")
    db.add(group)
    await db.flush()
    print(f"  ✓ Group: {group.name} (id={group.id})")
    return group


async def seed_user(db, group: Group) -> User:
    hashed = get_password_hash_sync("TestPass@2024x")
    user = User.create(
        email="test@university.dev",
        hashed_password=hashed,
        role=UserRole.STUDENT,
        is_active=True,
    )
    user.group_id = group.id
    db.add(user)
    await db.flush()

    profile = UserProfile(
        user_id=user.id,
        full_name="Тест Студентов",
        about="Тестовый студент для демонстрации возможностей платформы ГУУ.",
        telegram="@test_student_guu",
        status="Учусь, программирую, пью кофе ☕",
        avatar_url="https://picsum.photos/seed/avatar_test/256/256",
    )
    edu = EducationPath(
        user_id=user.id,
        institute="Институт информационных технологий",
        course="3",
        education_level="Бакалавриат",
        track="Программная инженерия",
        program="Информационные системы и технологии",
        record_book_number="ЗИ-301-042",
    )
    db.add(profile)
    db.add(edu)
    await db.flush()
    print(f"  ✓ User: {user.email} (id={user.id})")
    return user


async def seed_news(db, user: User) -> None:
    for item in NEWS_DATA:
        news = News(
            title=item["title"],
            content=item["content"],
            author_id=user.id,
            image_url=item["image_url"],
        )
        db.add(news)
    await db.flush()
    print(f"  ✓ News: {len(NEWS_DATA)} articles")


async def seed_stories(db, user: User) -> None:
    now = datetime.now(UTC)
    far_future = now + timedelta(days=365)
    for item in STORIES_DATA:
        story = Story(
            title=item["title"],
            short_text=item["short_text"],
            cover_url=item["cover_url"],
            is_active=True,
            published_at=now,
            expires_at=far_future,  # bypass 24 h default
            created_by=user.id,
        )
        db.add(story)
    await db.flush()
    print(f"  ✓ Stories: {len(STORIES_DATA)} stories (expires in 1 year)")


async def seed_events(db, user: User) -> None:
    for item in EVENTS_DATA:
        ev = Event(
            title=item["title"],
            description=item["description"],
            location=item["location"],
            event_type=item["event_type"],
            starts_at=item["starts_at"],
            ends_at=item["ends_at"],
            image_url=item["image_url"],
            is_active=True,
            created_by=user.id,
        )
        db.add(ev)
    await db.flush()
    print(f"  ✓ Events: {len(EVENTS_DATA)} events")


async def seed_schedule(db, group: Group, user: User) -> None:
    rows = 0
    for weekday, pair_num, subject, teacher, room, lesson_type, parity in SCHEDULE_DATA:
        base = _DAY_BASE[weekday]
        start, end = _pair(base, pair_num)
        entry = Schedule(
            group_id=group.id,
            creator_id=user.id,
            subject=subject,
            teacher=teacher,
            room=room,
            weekday=weekday,
            start_time=start,
            end_time=end,
            parity=parity,
            lesson_type=lesson_type,
        )
        db.add(entry)
        rows += 1
    await db.flush()
    print(f"  ✓ Schedule: {rows} entries (odd + even weeks)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    print("Initialising database connection…")
    init_database()

    async with async_session() as db:
        try:
            group = await seed_group(db)
            user = await seed_user(db, group)
            await seed_news(db, user)
            await seed_stories(db, user)
            await seed_events(db, user)
            await seed_schedule(db, group, user)
            await db.commit()
            print("\nAll demo data committed successfully.")
            print("Login: test@university.dev / TestPass@2024x")
        except IntegrityError as exc:
            await db.rollback()
            # Check if it's a duplicate-key error (already seeded)
            msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                print("\n⚠ Data already exists — skipped (no changes made).")
                print("  To reseed, truncate the tables first.")
            else:
                print(f"\n✗ IntegrityError: {exc}")
                raise


if __name__ == "__main__":
    asyncio.run(main())
