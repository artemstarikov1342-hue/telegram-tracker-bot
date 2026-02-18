"""
Конфигурация для Telegram бота и Яндекс.Трекера
"""
import os
from typing import Dict, Optional
from datetime import datetime, timedelta

# Telegram настройки
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')

# Яндекс.Трекер настройки
YANDEX_TRACKER_TOKEN = os.getenv('YANDEX_TRACKER_TOKEN', 'YOUR_YANDEX_TRACKER_TOKEN')
YANDEX_ORG_ID = os.getenv('YANDEX_ORG_ID', 'YOUR_ORG_ID')

# Webhook для уведомлений от Яндекс.Трекера
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your_secret_key_change_me')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8443'))

# Маппинг отделов на очереди
DEPARTMENT_MAPPING: Dict[str, Dict[str, Optional[str]]] = {
    'mgr': {
        'name': 'Менеджер',
        'queue': 'MNG',
        'assignee': None,
        'hashtag': '#mgr'
    },
    'hr': {
        'name': 'HR',
        'queue': 'HR',
        'assignee': None,
        'hashtag': '#hr'
    },
    'cc': {
        'name': 'Колл-центр',
        'queue': 'CC',
        'assignee': None,
        'hashtag': '#cc'
    },
    'razrab': {
        'name': 'Разработка',
        'queue': 'RAZRAB',
        'assignee': None,
        'hashtag': '#razrab'
    },
    'owner': {
        'name': 'Владелец',
        'queue': 'OWNER',
        'assignee': None,
        'hashtag': '#owner'
    },
    'buy': {
        'name': 'Закупки',
        'queue': 'BUYING',
        'assignee': None,
        'hashtag': '#buy'
    },
    'comm': {
        'name': 'Коммуникации',
        'queue': 'COMM',
        'assignee': None,
        'hashtag': '#comm'
    },
    'head': {
        'name': 'Руководство',
        'queue': 'HEAD',
        'assignee': None,
        'hashtag': '#head'
    },
}

# Список ID менеджеров (которые могут создавать и завершать задачи)
MANAGER_IDS = [
    8337630955,  # Менеджер 1
    # Добавь сюда Telegram ID других менеджеров
    # Узнать свой ID: напиши /info в чате с ботом
]

# Назначение исполнителей для партнеров
# Формат: 'ID партнера': 'login исполнителя в Яндекс.Трекере'
PARTNER_ASSIGNEES = {
    '2': 'artemiy-starikov',      # WEB#2 → artemiy-starikov
    '3': 'artemiy-starikov',      # WEB#3 → artemiy-starikov
    '5': 'artemiy-starikov',      # WEB#5 → artemiy-starikov
    '321': 'artemiy-starikov',    # WEB#321 → artemiy-starikov
    # Добавляй новых партнеров здесь:
    # '25': 'manager2',           # WEB#25 → manager2
}

# Исполнитель по умолчанию для новых партнеров (если не указан в PARTNER_ASSIGNEES)
DEFAULT_PARTNER_ASSIGNEE = 'artemiy-starikov'

# Паттерн для определения ID партнера в сообщении
# Формат: WEB#123 или WEB 123 или WEB123, где 123 - ID партнера
PARTNER_ID_PATTERN = r'WEB\s*#?\s*(\d+)'  # Гибкое регулярное выражение

# Очередь для всех партнерских задач
PARTNERS_QUEUE = 'PARTNERS'  # Все задачи партнеров в одной очереди

# Автоматическое создание досок для партнеров
# ВНИМАНИЕ: Пока отключено из-за дублирования. Создавайте доски вручную в Трекере.
AUTO_CREATE_BOARDS = False  # True = создавать доски автоматически

# Кэш партнеров (заполняется автоматически при создании задач)
# Хранит маппинг ID партнера → информация о доске
# Пример: {'2': {'board_id': 123, 'board_name': 'WEB2', 'tag': 'WEB2'}}
PARTNER_CACHE = {}

# Настройки задач по умолчанию
DEFAULT_PRIORITY = 'critical'  # Критический приоритет по умолчанию
DEFAULT_DEADLINE_DAYS = 0  # Дедлайн сегодня (0 дней от текущей даты)
DEFAULT_QUEUE = 'MNG'  # Очередь менеджеров по умолчанию

# Теги для парсинга
TASK_HASHTAG = '#задача'

# Возможные хештеги отделов (синонимы)
DEPARTMENT_HASHTAGS = {
    '#mgr': 'mgr',
    '#менедж': 'mgr',
    '#менеджер': 'mgr',
    '#hr': 'hr',
    '#cc': 'cc',
    '#razrab': 'razrab',
    '#owner': 'owner',
    '#buy': 'buy',
    '#comm': 'comm',
    '#head': 'head',
}

# Статусы для отслеживания завершения
COMPLETED_STATUSES = ['closed', 'resolved', 'done', 'завершена', 'закрыта']

# Логирование
LOG_LEVEL = 'INFO'
LOG_FILE = 'bot.log'

# База данных для хранения связей задач и чатов
DATABASE_FILE = 'tasks_db.json'
