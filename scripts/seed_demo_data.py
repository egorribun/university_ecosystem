"""
Seed script — creates demo data after a fresh Docker install.

Usage:
    python scripts/live_stand.py seed --demo

Run through the owner-checked live stand command, or the narrowly scoped
admin-smoke GitHub workflow target. Direct execution against any other database
fails closed.
"""

import asyncio
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

if "DATABASE_URL" not in os.environ:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.auth.security import get_password_hash_sync
from app.core.database import async_session, init_database
from app.models.chat import Chat, chat_participants
from app.models.enums import UserRole
from app.models.events import Event
from app.models.news import News
from app.models.schedule import Group, Schedule
from app.models.stories import Story
from app.models.users import EducationPath, User, UserProfile
from scripts.seed_target import require_owned_live_stand_target

DEMO_PEER_EMAIL = "demo.peer@example.test"
DEMO_PEER_USER_SEED_KEY = "ue-demo-v1:user:primary-peer"
DEMO_SECOND_PEER_EMAIL = "demo.peer.two@example.test"
DEMO_SECOND_PEER_USER_SEED_KEY = "ue-demo-v1:user:secondary-peer"
DEMO_PRIMARY_USER_EMAIL = "test@university.dev"
DEMO_PRIMARY_USER_SEED_KEY = "ue-demo-v1:user:primary-owner"
DEMO_CLASS_GROUP_SEED_KEY = "ue-demo-v1:group:class"
DEMO_DM_SEED_KEY = "ue-demo-v1:messenger:dm-primary-peer"
DEMO_GROUP_SEED_KEY = "ue-demo-v1:messenger:group"
DEMO_GROUP_NAME = "University Ecosystem Demo Group"

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


def _add_english_fields(
    records: list[dict], translations: list[dict[str, str]]
) -> None:
    if len(records) != len(translations):
        raise RuntimeError("English demo content must match the Russian records")
    for record, translation in zip(records, translations, strict=True):
        record.update({f"{field}_en": value for field, value in translation.items()})


_add_english_fields(
    NEWS_DATA,
    [
        {
            "title": "GUU ranks among the country's top 20 universities",
            "content": "The annual national ranking placed State University of Management 18th among Russia's leading universities. Progress in digital learning, research publications, and graduate employment helped raise the result.",
        },
        {
            "title": "Applications open for the international AI conference",
            "content": "The Department of Information Technology invites research submissions for the 16th International Conference on Intelligent Systems and Technologies. Abstracts are due May 15, 2026; participation is free for university students and postgraduate students.",
        },
        {
            "title": "GUU students win the FinTech Challenge 2026 hackathon",
            "content": "The Byte and Code team from the Institute of Information Technology won the national financial technology hackathon. Their machine-learning borrower scoring system was built in 48 hours, earning a cash prize and internship offers from three major banks.",
        },
        {
            "title": "New robotics lab opens in Building A",
            "content": "A new robotics and industrial automation lab has opened through the Priority 2030 program. It includes industrial robot arms, machine vision, and control-system workstations for eligible students.",
        },
        {
            "title": "Open Day takes place on April 12",
            "content": "Prospective students and their families are invited to meet faculty, tour the campus, and learn about university programs and admissions. Registration is available online.",
        },
        {
            "title": "Sechenov scholarships for medical students",
            "content": "Applications are open for scholarships supporting medical students with strong academic results and research interests. The award recognizes outstanding work in healthcare and biomedical studies.",
        },
        {
            "title": "Healthy Campus spring sports festival",
            "content": "The spring festival brings students together for team sports, fitness activities, and friendly competitions. Join the campus community for an active day outdoors.",
        },
        {
            "title": "Partnership agreement signed with Yandex Education",
            "content": "The university and Yandex Education will develop joint learning programs, practical projects, and career opportunities for students in technology and digital fields.",
        },
        {
            "title": "Student startup competition: apply by May 5",
            "content": "Student teams can submit startup ideas for expert review and partner support. Selected projects will receive mentoring and the chance to present at the final showcase.",
        },
        {
            "title": "New AI Ethics course opens to all programs",
            "content": "The interdisciplinary course explores responsible AI, bias, privacy, and the social impact of automated systems. Students from every program are welcome to enroll.",
        },
    ],
)

_add_english_fields(
    STORIES_DATA,
    [
        {
            "title": "🎓 Exam season: preparation tips",
            "short_text": "Seven proven ways to prepare for exams, shared by senior students.",
        },
        {
            "title": "📢 Open lecture: Web 3.0",
            "short_text": "Tomorrow at 18:00 in room 301: a lecture on decentralized application architecture.",
        },
        {
            "title": "🏆 We won!",
            "short_text": "A GUU team took first place at the regional programming championship.",
        },
        {
            "title": "☕ New café in Building B",
            "short_text": "A student café has opened with breakfasts from 99 rubles. Open from 08:00.",
        },
        {
            "title": "📚 Library updates its catalog",
            "short_text": "More than 200 new books on programming, data science, and cybersecurity are now available.",
        },
        {
            "title": "🎸 Student band rehearsal",
            "short_text": "The student rock band Zero Pointer is looking for a drummer. Auditions are Friday at 17:00.",
        },
        {
            "title": "🌱 Campus cleanup day",
            "short_text": "Join the spring campus cleanup this Saturday. Meet at 10:00 by Building A.",
        },
        {
            "title": "💼 Career fair",
            "short_text": "April 15 is Career Day. More than 40 companies are looking for interns and graduates.",
        },
        {
            "title": "🔬 GUU Science Day",
            "short_text": "Explore student research projects and vote for your favorite to win partner prizes.",
        },
        {
            "title": "🍕 Faculty pizza evening",
            "short_text": "Friday at 19:00 in the IT Institute lobby: an informal gathering with classmates and faculty.",
        },
        {
            "title": "📱 Mobile app update",
            "short_text": "Version 2.5 adds push notifications for classes and a new group chat.",
        },
        {
            "title": "🎨 Student exhibition",
            "short_text": "A gallery in Building C is showing fourth-year student design projects.",
        },
        {
            "title": "🏋️ Gym and martial arts",
            "short_text": "Sign up for martial arts by April 20 at the second-floor sports building.",
        },
        {
            "title": "🚀 Meetup: startups and IT careers",
            "short_text": "Graduates will share how they went from first-year students to CTOs. Wednesday at 18:30.",
        },
        {
            "title": "🌍 2026–27 exchange program",
            "short_text": "Applications are open for academic exchange at universities in Germany and Finland.",
        },
    ],
)

_add_english_fields(
    EVENTS_DATA,
    [
        {
            "title": "Open lecture: The future of AI in education",
            "description": "Professor Andrey Volkov of Moscow State University will discuss generative models in teaching, automated assessment, and personalized learning paths.",
            "location": "Assembly Hall, Building A, GUU",
            "event_type": "lecture",
        },
        {
            "title": "Workshop: FastAPI from zero to production",
            "description": "Build a REST API in this practical one-day workshop. Participants will create a complete microservice with authentication, tests, and a Docker build.",
            "location": "Lab 204, Building B",
            "event_type": "workshop",
        },
        {
            "title": "Algorithmic programming olympiad",
            "description": "An open team competition for groups of two or three. Solve ten Codeforces problems in five hours for a share of the 120,000-ruble prize fund.",
            "location": "Computer Lab 315, Building G",
            "event_type": "competition",
        },
        {
            "title": "Spring concert of student arts groups",
            "description": "The annual concert features the GUU choir, student theater, dance groups, and vocal ensembles. Admission is free with a student ID.",
            "location": "Grand Assembly Hall",
            "event_type": "cultural",
        },
        {
            "title": "IT Career Fair",
            "description": "More than 40 partner companies will present internships and jobs for students and graduates in IT fields.",
            "location": "Grand Assembly Hall and Building A foyer",
            "event_type": "workshop",
        },
        {
            "title": "Digital University hackathon",
            "description": "A 48-hour hackathon to build digital services for the university ecosystem, including scheduling, notifications, and academic analytics.",
            "location": "GUU Tech Hub coworking space, Building C",
            "event_type": "competition",
        },
        {
            "title": "Masterclass: public speaking and pitching",
            "description": "Rhetoric coach Elena Smirnova will lead practical exercises on startup pitch structure, voice, and presentation to investors.",
            "location": "Room 118, Building A",
            "event_type": "workshop",
        },
        {
            "title": "GUU mini-football championship",
            "description": "An interfaculty knockout tournament. Teams of eight may apply; matches take place on weekends throughout May.",
            "location": "GUU Sports Complex, Field 1",
            "event_type": "sports",
        },
        {
            "title": "IT Institute thesis project defenses 2026",
            "description": "Students from the Institute of Information Technology will present their final qualification projects. Visitors are welcome to attend and ask questions.",
            "location": "Conference Hall, third floor, Building B",
            "event_type": "lecture",
        },
        {
            "title": "Class of 2026 graduation ceremony",
            "description": "Celebrate the 2026 graduates with remarks from the rector, award presentations, and a reception.",
            "location": "GUU Central Assembly Hall",
            "event_type": "cultural",
        },
    ],
)

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


def _demo_user_profile(user_id) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        full_name="Тест Студентов",
        about="Тестовый студент для демонстрации возможностей платформы ГУУ.",
        telegram="@test_student_guu",
        status="Учусь, программирую, пью кофе ☕",
        avatar_url="https://picsum.photos/seed/avatar_test/256/256",
    )


def _demo_education_path(user_id) -> EducationPath:
    return EducationPath(
        user_id=user_id,
        institute="Институт информационных технологий",
        course="3",
        education_level="Бакалавриат",
        track="Программная инженерия",
        program="Информационные системы и технологии",
        record_book_number="ЗИ-301-042",
    )


async def seed_group(db) -> Group:
    owned_group = cast(
        Group | None,
        await db.scalar(
            select(Group).where(Group.demo_seed_key == DEMO_CLASS_GROUP_SEED_KEY)
        ),
    )
    if owned_group is not None:
        return owned_group

    canonical_group = cast(
        Group | None,
        await db.scalar(
            select(Group).where(
                Group.name == "ЗИ-301",
                Group.course == 3,
                Group.faculty == "Институт информационных технологий",
            )
        ),
    )
    if canonical_group is not None:
        raise RuntimeError(
            "canonical demo group is unowned; verify any legacy demo group and "
            "follow the migration's reviewed recovery note before seeding"
        )

    group = Group(
        name="ЗИ-301",
        course=3,
        faculty="Институт информационных технологий",
        demo_seed_key=DEMO_CLASS_GROUP_SEED_KEY,
    )
    db.add(group)
    await db.flush()
    print(f"  ✓ Group: {group.name} (id={group.id})")
    return group


async def seed_user(db, group: Group) -> User:
    existing = cast(
        User | None,
        await db.scalar(select(User).where(User.email == DEMO_PRIMARY_USER_EMAIL)),
    )
    key_owner = cast(
        User | None,
        await db.scalar(
            select(User).where(User.demo_seed_key == DEMO_PRIMARY_USER_SEED_KEY)
        ),
    )
    if existing is not None:
        if key_owner is None or key_owner.id != existing.id:
            raise RuntimeError(
                "canonical demo account is unowned; verify any legacy demo account "
                "and follow the migration's reviewed recovery note before seeding"
            )
        if existing.role != UserRole.STUDENT:
            raise ValueError("refusing to change the role of an existing demo account")
        profile_exists = await db.scalar(
            select(UserProfile.user_id).where(UserProfile.user_id == existing.id)
        )
        if profile_exists is None:
            db.add(_demo_user_profile(existing.id))
        education_exists = await db.scalar(
            select(EducationPath.user_id).where(EducationPath.user_id == existing.id)
        )
        if education_exists is None:
            db.add(_demo_education_path(existing.id))
        await db.flush()
        return existing

    if key_owner is not None:
        raise RuntimeError("canonical demo account ownership key is already occupied")

    hashed = get_password_hash_sync("TestPass@2024x")
    user = User.create(
        email=DEMO_PRIMARY_USER_EMAIL,
        hashed_password=hashed,
        role=UserRole.STUDENT,
        is_active=True,
    )
    user.group_id = group.id
    user.demo_seed_key = DEMO_PRIMARY_USER_SEED_KEY
    db.add(user)
    await db.flush()

    profile = _demo_user_profile(user.id)
    edu = _demo_education_path(user.id)
    db.add(profile)
    db.add(edu)
    await db.flush()
    print(f"  ✓ User: {user.email} (id={user.id})")
    return user


async def _seed_demo_peer_user(
    db: AsyncSession,
    group: Group,
    *,
    email: str,
    seed_key: str,
    full_name: str,
) -> User:
    if not email.casefold().endswith(".test"):
        raise RuntimeError("synthetic demo peer identity must use the .test domain")

    existing = cast(
        User | None, await db.scalar(select(User).where(User.email == email))
    )
    key_owner = cast(
        User | None,
        await db.scalar(select(User).where(User.demo_seed_key == seed_key)),
    )
    if existing is not None:
        if (
            existing.role is not UserRole.STUDENT
            or key_owner is None
            or key_owner.id != existing.id
        ):
            raise RuntimeError("reserved demo peer identity is occupied")
        return existing

    if key_owner is not None:
        raise RuntimeError("reserved demo peer ownership key is occupied")

    # The raw value is deliberately ephemeral: only its Argon2id hash is stored,
    # so this synthetic participant cannot be logged into with a seeded password.
    # Guarantee every required character class without reducing random entropy.
    hashed_password = get_password_hash_sync(secrets.token_urlsafe(32) + "!Aa0")
    peer = User.create(
        email=email,
        hashed_password=hashed_password,
        role=UserRole.STUDENT,
        is_active=True,
    )
    peer.group_id = group.id
    peer.demo_seed_key = seed_key
    db.add(peer)
    await db.flush()

    db.add(
        UserProfile(
            user_id=peer.id,
            full_name=full_name,
            about="Synthetic participant for the live demo.",
        )
    )
    db.add(
        EducationPath(
            user_id=peer.id,
            institute="Demo University",
            course="3",
            education_level="Bachelor",
            track="General Studies",
            program="Synthetic Demo Program",
        )
    )
    await db.flush()
    print("  ✓ Synthetic Messenger peer prepared")
    return peer


async def seed_demo_peer_user(db: AsyncSession, group: Group) -> User:
    """Create or verify the reserved non-loginable primary synthetic peer."""
    return await _seed_demo_peer_user(
        db,
        group,
        email=DEMO_PEER_EMAIL,
        seed_key=DEMO_PEER_USER_SEED_KEY,
        full_name="Synthetic Demo Student",
    )


async def seed_demo_second_peer_user(db: AsyncSession, group: Group) -> User:
    """Create or verify the second reserved non-loginable synthetic peer."""
    return await _seed_demo_peer_user(
        db,
        group,
        email=DEMO_SECOND_PEER_EMAIL,
        seed_key=DEMO_SECOND_PEER_USER_SEED_KEY,
        full_name="Synthetic Demo Student Two",
    )


async def _invalidate_demo_chat_caches(
    chat_id: UUID, participant_ids: tuple[UUID, ...]
) -> None:
    from app.api.ws.presence import (
        invalidate_chat_participants_cache,
        invalidate_presence_audience_cache,
    )

    await invalidate_chat_participants_cache(chat_id)
    await invalidate_presence_audience_cache(*participant_ids)


async def seed_demo_dm(db: AsyncSession, owner: User, peer: User) -> Chat:
    """Ensure the live-demo pair has one normal two-member Messenger DM."""
    if owner.id is None or peer.id is None or owner.id == peer.id:
        raise RuntimeError("demo DM participants must be distinct")

    chat = cast(
        Chat | None,
        await db.scalar(
            select(Chat)
            .where(Chat.demo_seed_key == DEMO_DM_SEED_KEY)
            .options(selectinload(Chat.participants))
        ),
    )
    expected_ids = {owner.id, peer.id}
    if chat is not None:
        actual_ids = {participant.id for participant in chat.participants}
        if chat.chat_type != "dm" or actual_ids != expected_ids:
            raise RuntimeError("demo DM ownership key has drifted")
        return chat

    existing_pair = (
        await db.scalars(_exact_chat_membership_query((owner, peer), "dm"))
    ).all()
    if existing_pair:
        raise RuntimeError("reserved demo DM participant pair is already occupied")

    chat = Chat(chat_type="dm", demo_seed_key=DEMO_DM_SEED_KEY)
    chat.participants.append(owner)
    chat.participants.append(peer)
    db.add(chat)
    await db.flush()
    await _invalidate_demo_chat_caches(chat.id, (owner.id, peer.id))
    print("  ✓ Synthetic Messenger DM prepared")
    return chat


def _exact_chat_membership_query(
    users: tuple[User, ...], chat_type: str
) -> Select[tuple[Chat]]:
    participant_chats = [
        select(chat_participants.c.chat_id).where(
            chat_participants.c.user_id == user.id
        )
        for user in users
    ]
    participant_count = (
        select(func.count())
        .where(chat_participants.c.chat_id == Chat.id)
        .correlate(Chat)
        .scalar_subquery()
    )
    return (
        select(Chat)
        .where(
            Chat.chat_type == chat_type,
            *(Chat.id.in_(chat_ids) for chat_ids in participant_chats),
            participant_count == len(users),
        )
        .options(selectinload(Chat.participants))
    )


async def seed_demo_group(db: AsyncSession, owner: User, peers: list[User]) -> Chat:
    """Seed one named group, keyed privately and guarded against stale peers."""
    participants = (owner, *peers)
    participant_ids = [participant.id for participant in participants]
    if (
        len(peers) != 2
        or any(participant_id is None for participant_id in participant_ids)
        or len(set(participant_ids)) != 3
        or peers[0].email != DEMO_PEER_EMAIL
        or peers[1].email != DEMO_SECOND_PEER_EMAIL
        or any(peer.role is not UserRole.STUDENT for peer in peers)
    ):
        raise RuntimeError("demo group requires the reserved synthetic participants")

    chat = cast(
        Chat | None,
        await db.scalar(
            select(Chat)
            .where(Chat.demo_seed_key == DEMO_GROUP_SEED_KEY)
            .options(selectinload(Chat.participants))
        ),
    )
    expected_ids = set(participant_ids)
    if chat is not None:
        actual_ids = {participant.id for participant in chat.participants}
        if chat.chat_type != "group" or actual_ids != expected_ids:
            raise RuntimeError("demo group ownership key has drifted")
        return chat

    # A migration rollback removes only the nullable key column. The reserved
    # peers remain, so any group using either peer is ambiguous and blocks seed
    # creation instead of being adopted or duplicated on re-upgrade.
    peer_chats = select(chat_participants.c.chat_id).where(
        chat_participants.c.user_id.in_([peers[0].id, peers[1].id])
    )
    unmarked_peer_groups = (
        await db.scalars(
            select(Chat)
            .where(Chat.chat_type == "group", Chat.id.in_(peer_chats))
            .options(selectinload(Chat.participants))
        )
    ).all()
    if unmarked_peer_groups:
        raise RuntimeError("reserved demo group peer membership is already occupied")

    chat = Chat(
        chat_type="group",
        name=DEMO_GROUP_NAME,
        created_by=owner.id,
        demo_seed_key=DEMO_GROUP_SEED_KEY,
    )
    chat.participants.extend(participants)
    db.add(chat)
    await db.flush()
    await _invalidate_demo_chat_caches(chat.id, tuple(sorted(participant_ids, key=str)))
    print("  ✓ Synthetic Messenger group prepared")
    return chat


async def seed_news(db, user: User) -> None:
    for item in NEWS_DATA:
        existing_seed = await db.scalar(
            select(News).where(
                News.title == item["title"],
                News.author_id == user.id,
            )
        )
        if existing_seed is not None:
            if existing_seed.content == item["content"]:
                if not existing_seed.title_en:
                    existing_seed.title_en = item["title_en"]
                if not existing_seed.content_en:
                    existing_seed.content_en = item["content_en"]
            continue
        title_collision = await db.scalar(
            select(News).where(News.title == item["title"])
        )
        if title_collision is not None:
            continue
        news = News(
            title=item["title"],
            title_en=item["title_en"],
            content=item["content"],
            content_en=item["content_en"],
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
        existing_seed = await db.scalar(
            select(Story).where(
                Story.title == item["title"],
                Story.created_by == user.id,
            )
        )
        if existing_seed is not None:
            # Backfill only a seed row whose source-language content is intact.
            # Preserve every populated translation; lifecycle changes require
            # the populated translations to be canonical as well.
            canonical_content_matches = (
                all(
                    getattr(existing_seed, field) == item[field]
                    for field in ("title", "short_text", "cover_url")
                )
                and getattr(existing_seed, "cta_url", None) is None
            )
            canonical_translations_match = all(
                getattr(existing_seed, field, None) in (None, item.get(field))
                for field in ("title_en", "short_text_en")
            )
            if canonical_content_matches:
                for field in ("title_en", "short_text_en"):
                    canonical_translation = item.get(field)
                    if canonical_translation and not getattr(existing_seed, field):
                        setattr(existing_seed, field, canonical_translation)
            if canonical_content_matches and canonical_translations_match:
                expires_at = existing_seed.expires_at
                if expires_at is not None:
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=UTC)
                    else:
                        expires_at = expires_at.astimezone(UTC)
                    if expires_at <= now:
                        existing_seed.is_active = True
                        existing_seed.expires_at = far_future
            continue
        title_collision = await db.scalar(
            select(Story).where(Story.title == item["title"])
        )
        if title_collision is not None:
            continue
        story = Story(
            title=item["title"],
            title_en=item.get("title_en"),
            short_text=item["short_text"],
            short_text_en=item.get("short_text_en"),
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
        existing_seed = await db.scalar(
            select(Event).where(
                Event.title == item["title"],
                Event.starts_at == item["starts_at"],
                Event.created_by == user.id,
            )
        )
        if existing_seed is not None:
            source_matches = all(
                getattr(existing_seed, field) == item[field]
                for field in ("description", "location", "event_type")
            )
            if source_matches:
                for field in (
                    "title_en",
                    "description_en",
                    "location_en",
                    "event_type_en",
                ):
                    if not getattr(existing_seed, field):
                        setattr(existing_seed, field, item[field])
            continue
        natural_key_collision = await db.scalar(
            select(Event).where(
                Event.title == item["title"],
                Event.starts_at == item["starts_at"],
            )
        )
        if natural_key_collision is not None:
            continue
        ev = Event(
            title=item["title"],
            title_en=item["title_en"],
            description=item["description"],
            description_en=item["description_en"],
            location=item["location"],
            location_en=item["location_en"],
            event_type=item["event_type"],
            event_type_en=item["event_type_en"],
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
    existing_rows = await db.scalars(
        select(Schedule).where(Schedule.group_id == group.id)
    )
    existing_keys = {
        (
            entry.weekday,
            entry.start_time.replace(tzinfo=UTC)
            if entry.start_time.tzinfo is None
            else entry.start_time.astimezone(UTC),
            entry.parity,
            entry.subject,
        )
        for entry in existing_rows.all()
    }
    for weekday, pair_num, subject, teacher, room, lesson_type, parity in SCHEDULE_DATA:
        base = _DAY_BASE[weekday]
        start, end = _pair(base, pair_num)
        key = (weekday, start, parity, subject)
        if key in existing_keys:
            continue
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
        existing_keys.add(key)
        rows += 1
    await db.flush()
    print(f"  ✓ Schedule: {rows} entries (odd + even weeks)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _is_live_stand_demo_target(project: str) -> bool:
    return (
        os.environ.get("UE_SEED_TARGET") is None
        and os.environ.get("LIVE_STAND_OWNER_VERIFIED") == "1"
        and os.environ.get("LIVE_STAND_SEED_PROJECT") == project
        and os.environ.get("COMPOSE_PROJECT_NAME") == project
    )


async def main() -> None:
    target_project = require_owned_live_stand_target()
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
            if _is_live_stand_demo_target(target_project):
                peer = await seed_demo_peer_user(db, group)
                second_peer = await seed_demo_second_peer_user(db, group)
                await seed_demo_dm(db, user, peer)
                await seed_demo_group(db, user, [peer, second_peer])
            await db.commit()
            print("\nAll demo data committed successfully.")
        except IntegrityError:
            await db.rollback()
            raise RuntimeError(
                "demo seed transaction failed and was rolled back"
            ) from None


if __name__ == "__main__":
    asyncio.run(main())
