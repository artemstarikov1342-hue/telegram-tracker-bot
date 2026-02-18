"""
Telegram бот для интеграции с Яндекс.Трекером
"""
# Загрузка переменных окружения из .env
from dotenv import load_dotenv
load_dotenv()

import logging
import re
import random
import string
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import (
    TELEGRAM_BOT_TOKEN,
    YANDEX_TRACKER_TOKEN,
    YANDEX_ORG_ID,
    DEPARTMENT_MAPPING,
    DEPARTMENT_HASHTAGS,
    TASK_HASHTAG,
    DEFAULT_QUEUE,
    DEFAULT_PRIORITY,
    DEFAULT_DEADLINE_DAYS,
    LOG_LEVEL,
    DATABASE_FILE,
    MANAGER_IDS,
    AUTO_CREATE_BOARDS,
    PARTNERS_QUEUE,
    PARTNER_ID_PATTERN,
    PARTNER_ASSIGNEES,
    DEFAULT_PARTNER_ASSIGNEE,
    PARTNER_CACHE,
    COMPLETED_STATUSES
)
from yandex_tracker import YandexTrackerClient
from database import TaskDatabase

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)


class TrackerBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.tracker_client = YandexTrackerClient(
            token=YANDEX_TRACKER_TOKEN,
            org_id=YANDEX_ORG_ID
        )
        self.db = TaskDatabase(DATABASE_FILE)
    
    def parse_task_from_message(self, message_text: str) -> Optional[str]:
        """
        Извлечение текста задачи из сообщения (только после #задача)
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Текст задачи или None
        """
        if TASK_HASHTAG not in message_text.lower():
            return None
        
        # Находим позицию #задача и берем текст после него
        match = re.search(r'#задача\s+(.*)', message_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            task_text = match.group(1).strip()
            # Удаляем хештеги отделов из текста задачи
            for hashtag in DEPARTMENT_HASHTAGS.keys():
                task_text = re.sub(rf'{hashtag}\s*', '', task_text, flags=re.IGNORECASE)
            # Удаляем WEB#123 из текста задачи (остается в логах для маршрутизации)
            task_text = re.sub(PARTNER_ID_PATTERN, '', task_text, flags=re.IGNORECASE)
            return task_text.strip()
        
        return None
    
    def get_departments_from_message(self, message_text: str) -> List[str]:
        """
        Извлечение всех отделов из хештегов в сообщении
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Список кодов отделов
        """
        departments = []
        message_lower = message_text.lower()
        
        for hashtag, dept_code in DEPARTMENT_HASHTAGS.items():
            if hashtag in message_lower:
                if dept_code not in departments:
                    departments.append(dept_code)
        
        return departments
    
    def parse_department_task(self, message_text: str) -> Optional[dict]:
        """
        Парсинг задачи из формата #отдел Текст задачи (без #задача)
        Например: #hr Нанять дизайнера
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            dict с ключами 'dept_code', 'task_text' или None
        """
        message_lower = message_text.lower().strip()
        
        for hashtag, dept_code in DEPARTMENT_HASHTAGS.items():
            if message_lower.startswith(hashtag):
                # Извлекаем текст после хэштега
                task_text = message_text[len(hashtag):].strip()
                if task_text:
                    return {
                        'dept_code': dept_code,
                        'task_text': task_text
                    }
        
        return None
    
    def is_manager(self, user_id: int) -> bool:
        """
        Проверить, является ли пользователь менеджером
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            True если менеджер, False иначе
        """
        return user_id in MANAGER_IDS
    
    def extract_partner_id(self, message_text: str) -> Optional[str]:
        """
        Извлечь ID партнера из текста сообщения
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            ID партнера (например: '123' из 'WEB#123') или None
        """
        logger.info(f"🔍 Ищу ID партнера в сообщении: '{message_text[:50]}...'")
        match = re.search(PARTNER_ID_PATTERN, message_text, re.IGNORECASE)
        if match:
            partner_id = match.group(1)
            logger.info(f"✅ Найден ID партнера: {partner_id} (WEB#{partner_id})")
            return partner_id
        logger.warning(f"⚠️ ID партнера НЕ найден! Паттерн: {PARTNER_ID_PATTERN}")
        return None
    
    def get_partner_tag(self, partner_id: str) -> str:
        """
        Получить тег для партнера по его ID
        
        Args:
            partner_id: ID партнера (например: '2', '25', '123')
            
        Returns:
            Тег партнера (например: 'WEB2', 'WEB25', 'WEB123')
        """
        return f"WEB{partner_id}"
    
    def get_or_create_partner_board(self, partner_id: str) -> Optional[Dict]:
        """
        Получить или создать доску для партнера
        
        Args:
            partner_id: ID партнера (например: '2', '25', '123')
            
        Returns:
            Информация о доске или None
        """
        partner_tag = self.get_partner_tag(partner_id)
        board_name = partner_tag  # Название доски = WEB2, WEB25, etc
        
        # Проверяем кэш
        if partner_id in PARTNER_CACHE:
            logger.info(f"ℹ️ Доска для партнера {partner_tag} найдена в кэше")
            return PARTNER_CACHE[partner_id]
        
        # Если включено автосоздание досок
        if AUTO_CREATE_BOARDS:
            # Создаем доску с фильтром по тегу
            board_info = self.tracker_client.create_board(
                board_name=board_name,
                queue=PARTNERS_QUEUE,
                filter_tag=partner_tag
            )
            
            if board_info:
                logger.info(f"✅ Создана доска {board_name} для партнера WEB#{partner_id}")
                # Добавляем в кэш
                PARTNER_CACHE[partner_id] = {
                    'board_id': board_info.get('id'),
                    'board_name': board_name,
                    'tag': partner_tag,
                    'partner_id': partner_id
                }
                return PARTNER_CACHE[partner_id]
            else:
                logger.warning(f"⚠️ Не удалось создать доску для {partner_tag}")
                # Сохраняем в кэш без board_id
                PARTNER_CACHE[partner_id] = {
                    'board_id': None,
                    'board_name': board_name,
                    'tag': partner_tag,
                    'partner_id': partner_id
                }
                return PARTNER_CACHE[partner_id]
        
        return None
    
    def get_deadline_date(self) -> str:
        """
        Получение даты дедлайна
        
        Returns:
            Дата в формате YYYY-MM-DD
        """
        deadline = datetime.now() + timedelta(days=DEFAULT_DEADLINE_DAYS)
        return deadline.strftime('%Y-%m-%d')
    
    async def handle_reply_comment(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Обработка ответа на сообщение бота — добавление комментария в задачу Трекера.
        
        Returns:
            True если это был reply-комментарий и он обработан, False иначе
        """
        if not message.reply_to_message:
            return False
        
        # Проверяем, что ответ на сообщение бота
        reply_msg = message.reply_to_message
        if not reply_msg.from_user or not reply_msg.from_user.is_bot:
            return False
        
        # Ищем ключ задачи в тексте сообщения бота (формат: QUEUE-123)
        reply_text = reply_msg.text or ''
        issue_keys = re.findall(r'[A-Z]+-\d+', reply_text)
        
        if not issue_keys:
            return False
        
        # Берём первый найденный ключ
        issue_key = issue_keys[0]
        comment_text = message.text.strip()
        username = message.from_user.username or message.from_user.first_name
        
        if not comment_text:
            return False
        
        # Добавляем комментарий в Трекер
        full_comment = f"💬 Комментарий от @{username}:\n\n{comment_text}"
        result = self.tracker_client.add_comment(issue_key, full_comment)
        
        if result:
            await message.reply_text(f"💬 Комментарий добавлен к задаче {issue_key}")
            logger.info(f"💬 Комментарий от {username} добавлен к {issue_key}")
        else:
            await message.reply_text(f"❌ Не удалось добавить комментарий к {issue_key}")
            logger.error(f"❌ Ошибка добавления комментария к {issue_key}")
        
        return True
    
    async def handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик всех сообщений.
        Поддерживает два формата:
        1. #отдел Текст задачи — доступно ВСЕМ пользователям
        2. #задача ... — только менеджеры (партнёрские задачи)
        3. Reply на сообщение бота — комментарий в задаче Трекера
        """
        if not update.message or not update.message.text:
            return
        
        # Проверяем reply-комментарий
        if await self.handle_reply_comment(update.message, context):
            return
        
        message = update.message
        message_text = message.text
        user_id = message.from_user.id
        chat_id = message.chat.id
        chat_type = message.chat.type
        username = message.from_user.username or message.from_user.first_name
        
        # === ПОТОК 1: Задачи по отделам (#hr, #cc, #razrab, etc.) — ВСЕ пользователи ===
        dept_task = self.parse_department_task(message_text)
        if dept_task:
            await self._handle_department_task(
                message, context, dept_task, user_id, chat_id, chat_type, username
            )
            return
        
        # === ПОТОК 2: Партнёрские задачи (#задача ...) — только менеджеры ===
        if TASK_HASHTAG.lower() not in message_text.lower():
            return
        
        # ПРОВЕРКА: Только менеджеры могут создавать партнёрские задачи
        if not self.is_manager(user_id):
            logger.warning(f"⚠️ ОТКАЗАНО: Пользователь {username} (ID: {user_id}) не является менеджером!")
            await message.reply_text(
                "❌ Только менеджеры могут создавать партнёрские задачи.\n"
                "Для задач в отделы используйте:\n"
                "#hr, #cc, #razrab, #owner, #buy, #comm, #head"
            )
            return
        
        logger.info(f"="*60)
        logger.info(f"🔔 Обнаружена задача от менеджера {username} (ID: {user_id})")
        logger.info(f"📱 Chat ID: {chat_id}")
        logger.info(f"💬 Тип чата: {chat_type}")
        logger.info(f"📝 Текст сообщения: {message_text[:100]}...")
        
        # Парсим текст задачи
        task_text = self.parse_task_from_message(message_text)
        if not task_text:
            await message.reply_text(
                "❌ Не удалось распознать задачу. "
                "Используйте формат:\n"
                f"{TASK_HASHTAG} Текст задачи\n\n"
                f"Для задач в отделы:\n"
                f"#hr, #cc, #razrab, #owner, #buy, #comm, #head"
            )
            return
        
        # Разделяем на название и описание
        lines = task_text.split('\n', 1)
        summary = lines[0].strip()
        description = lines[1].strip() if len(lines) > 1 else ""
        
        # Получаем отделы из хештегов
        departments = self.get_departments_from_message(message_text)
        logger.info(f"🏢 Найденные отделы: {departments if departments else 'нет'}")
        
        # Извлекаем ID партнера из текста сообщения (WEB#123)
        partner_id = self.extract_partner_id(message_text)
        partner_tag = None
        partner_name = None
        
        if partner_id:
            # Получаем тег для партнера
            partner_tag = self.get_partner_tag(partner_id)
            partner_name = f"WEB#{partner_id}"
            logger.info(f"🎯 ID партнера: {partner_id}, Тег: {partner_tag}")
        else:
            logger.info("ℹ️ ID партнера не указан в сообщении (формат: WEB#123)")
        
        # Формируем полное описание
        full_description = (
            f"📱 Задача создана из Telegram\n"
            f"👤 Автор: @{username} (ID: {user_id})\n"
            f"🏢 Партнер: {partner_name}\n"
            f"💬 Chat ID: {chat_id}\n"
        )
        
        if description:
            full_description += f"\n{description}"
        
        # Список созданных задач
        created_issues = []
        
        # Дедлайн
        deadline = self.get_deadline_date()
        
        # Создаем задачи в указанных отделах
        logger.info(f"🚀 Начинаем создание задач...")
        for dept_code in departments:
            dept_info = DEPARTMENT_MAPPING[dept_code]
            queue = dept_info['queue']
            logger.info(f"  → Создаём задачу в очереди {queue} (отдел: {dept_info['name']})")
            
            issue = self.tracker_client.create_issue(
                queue=queue,
                summary=summary,
                description=full_description + f"\n🏷️ Отдел: {dept_info['name']}",
                assignee=dept_info.get('assignee'),
                priority=DEFAULT_PRIORITY,
                deadline=deadline,
                tags=['telegram', dept_code, f'chat_{chat_id}']
            )
            
            if issue:
                issue_key = issue.get('key')
                created_issues.append({
                    'key': issue_key,
                    'queue': queue,
                    'department': dept_info['name']
                })
                
                # Сохраняем в БД
                self.db.add_task(
                    issue_key=issue_key,
                    chat_id=chat_id,
                    message_id=message.message_id,
                    summary=summary,
                    queue=queue,
                    department=dept_code,
                    creator_id=user_id
                )
                
                logger.info(f"Создана задача {issue_key} в очереди {queue}")
        
        # Создаем задачу для партнера (если указан ID)
        if partner_tag:
            # Сначала создаем/получаем доску для партнера
            partner_info = self.get_or_create_partner_board(partner_id)
            
            # Определяем исполнителя для партнера
            assignee = PARTNER_ASSIGNEES.get(partner_id, DEFAULT_PARTNER_ASSIGNEE)
            logger.info(f"  → Исполнитель для партнера {partner_id}: {assignee}")
            
            logger.info(f"  → Создаём задачу для партнера {partner_name} с тегом {partner_tag}")
            issue = self.tracker_client.create_issue(
                queue=PARTNERS_QUEUE,  # Все партнеры в одной очереди!
                summary=summary,
                description=full_description + f"\n🏷️ Партнер: {partner_name}",
                assignee=assignee,
                priority=DEFAULT_PRIORITY,
                deadline=deadline,
                tags=['telegram', 'partner', partner_tag, f'chat_{chat_id}']
            )
            
            if issue:
                issue_key = issue.get('key')
                created_issues.append({
                    'key': issue_key,
                    'queue': PARTNERS_QUEUE,
                    'department': f'Партнер {partner_tag}'
                })
                
                # Сохраняем в БД с тегом партнера
                self.db.add_task(
                    issue_key=issue_key,
                    chat_id=chat_id,
                    message_id=message.message_id,
                    summary=summary,
                    queue=PARTNERS_QUEUE,
                    department=partner_tag,
                    creator_id=user_id
                )
                
                logger.info(f"Создана задача {issue_key} в очереди {PARTNERS_QUEUE} с тегом {partner_tag}")
                
                if partner_info and partner_info.get('board_id'):
                    board_url = f"https://tracker.yandex.ru/boards/{partner_info['board_id']}"
                    logger.info(f"📊 Доска партнера: {board_url}")
        
        # Если не указаны отделы и нет партнера, создаем в общей очереди
        if not created_issues:
            logger.info(f"  → Создаём задачу в общей очереди {DEFAULT_QUEUE}")
            issue = self.tracker_client.create_issue(
                queue=DEFAULT_QUEUE,
                summary=summary,
                description=full_description,
                assignee=None,
                priority=DEFAULT_PRIORITY,
                deadline=deadline,
                tags=['telegram', f'chat_{chat_id}']
            )
            
            if issue:
                issue_key = issue.get('key')
                created_issues.append({
                    'key': issue_key,
                    'queue': DEFAULT_QUEUE,
                    'department': 'Общая'
                })
                
                self.db.add_task(
                    issue_key=issue_key,
                    chat_id=chat_id,
                    message_id=message.message_id,
                    summary=summary,
                    queue=DEFAULT_QUEUE,
                    creator_id=user_id
                )
                
                logger.info(f"Создана задача {issue_key} в общей очереди {DEFAULT_QUEUE}")
        
        # Формируем ответ
        logger.info(f"✅ Всего создано задач: {len(created_issues)}")
        for issue_info in created_issues:
            logger.info(f"  ✓ {issue_info['key']} в очереди {issue_info['queue']} ({issue_info['department']})")
        logger.info(f"="*60)
        
        if created_issues:
            # КОРОТКОЕ сообщение В ГРУППУ
            group_message = f"✅ Задача создана\n\n📝 {summary}"
            await message.reply_text(group_message)
            
            # ПОЛНОЕ сообщение В ЛС МЕНЕДЖЕРУ
            manager_message = "✅ Задача создана успешно!\n\n"
            manager_message += f"📝 Название: {summary}\n"
            manager_message += f"⚠️ Приоритет: {DEFAULT_PRIORITY}\n"
            manager_message += f"📅 Дедлайн: {deadline}\n\n"
            
            for idx, issue_info in enumerate(created_issues, 1):
                issue_url = f"https://tracker.yandex.ru/{issue_info['key']}"
                manager_message += (
                    f"{idx}. 📋 {issue_info['key']} ({issue_info['department']})\n"
                    f"   🔗 {issue_url}\n\n"
                )
            
            # Кнопка "Завершить задачу" (только первую задачу можно завершить)
            keyboard = [
                [InlineKeyboardButton(
                    "✅ Завершить задачу",
                    callback_data=f"complete_{created_issues[0]['key']}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем в ЛС менеджеру
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=manager_message,
                    reply_markup=reply_markup
                )
                logger.info(f"✅ Отправлено ЛС менеджеру {user_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ЛС менеджеру: {e}")
                # Если не удалось отправить ЛС, отправляем в группу
                await message.reply_text(
                    f"⚠️ Не удалось отправить детали в ЛС.\n"
                    f"Начните диалог с ботом командой /start",
                    reply_markup=reply_markup
                )
        else:
            await message.reply_text(
                "❌ Ошибка при создании задачи в Яндекс.Трекере. "
                "Проверьте настройки и попробуйте позже."
            )
    
    async def _handle_department_task(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE,
        dept_task: dict,
        user_id: int,
        chat_id: int,
        chat_type: str,
        username: str
    ) -> None:
        """
        Обработка задачи по отделу (#hr, #cc, #razrab, etc.)
        Доступно ВСЕМ пользователям бота.
        """
        dept_code = dept_task['dept_code']
        task_text = dept_task['task_text']
        
        dept_info = DEPARTMENT_MAPPING.get(dept_code)
        if not dept_info:
            logger.error(f"❌ Отдел {dept_code} не найден в DEPARTMENT_MAPPING")
            return
        
        queue = dept_info['queue']
        dept_name = dept_info['name']
        
        logger.info(f"="*60)
        logger.info(f"🔔 Задача в отдел {dept_name} от {username} (ID: {user_id})")
        logger.info(f"📱 Chat ID: {chat_id}, Тип: {chat_type}")
        logger.info(f"📝 Текст: {task_text[:100]}...")
        
        # Разделяем на название и описание
        lines = task_text.split('\n', 1)
        summary = lines[0].strip()
        description = lines[1].strip() if len(lines) > 1 else ""
        
        # Формируем описание
        full_description = (
            f"📱 Задача создана из Telegram\n"
            f"👤 Автор: @{username} (ID: {user_id})\n"
            f"🏢 Отдел: {dept_name}\n"
            f"💬 Chat ID: {chat_id}\n"
        )
        if description:
            full_description += f"\n{description}"
        
        deadline = self.get_deadline_date()
        
        # Создаём задачу в Трекере
        logger.info(f"🚀 Создаём задачу в очереди {queue} ({dept_name})")
        issue = self.tracker_client.create_issue(
            queue=queue,
            summary=summary,
            description=full_description,
            assignee=dept_info.get('assignee'),
            priority=DEFAULT_PRIORITY,
            deadline=deadline,
            tags=['telegram', dept_code, f'user_{user_id}', f'chat_{chat_id}']
        )
        
        if issue:
            issue_key = issue.get('key')
            issue_url = f"https://tracker.yandex.ru/{issue_key}"
            
            # Сохраняем в БД
            self.db.add_task(
                issue_key=issue_key,
                chat_id=chat_id,
                message_id=message.message_id,
                summary=summary,
                queue=queue,
                department=dept_code,
                creator_id=user_id
            )
            
            logger.info(f"✅ Создана задача {issue_key} в очереди {queue}")
            
            # Короткое сообщение в чат (группу или ЛС)
            if chat_type in ('group', 'supergroup'):
                group_msg = f"✅ Задача создана\n\n📝 {summary}\n🏢 Отдел: {dept_name}"
                await message.reply_text(group_msg)
            
            # Полное сообщение в ЛС создателю
            dm_message = (
                f"✅ Задача создана успешно!\n\n"
                f"📝 Название: {summary}\n"
                f"🏢 Отдел: {dept_name} ({queue})\n"
                f"⚠️ Приоритет: {DEFAULT_PRIORITY}\n"
                f"📅 Дедлайн: {deadline}\n\n"
                f"📋 {issue_key}\n"
                f"🔗 {issue_url}\n\n"
                f"Используйте /mytasks для просмотра ваших задач"
            )
            
            # Кнопка завершения
            keyboard = [
                [InlineKeyboardButton(
                    "✅ Завершить задачу",
                    callback_data=f"complete_{issue_key}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=dm_message,
                    reply_markup=reply_markup
                )
                logger.info(f"✅ Отправлено ЛС пользователю {user_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ЛС: {e}")
                # Если ЛС не удалось — отправляем в текущий чат
                await message.reply_text(
                    dm_message,
                    reply_markup=reply_markup
                )
        else:
            await message.reply_text(
                "❌ Ошибка при создании задачи в Яндекс.Трекере.\n"
                "Проверьте настройки и попробуйте позже."
            )
        
        logger.info(f"="*60)
    
    def sync_user_tasks_status(self, user_id: int) -> List[str]:
        """
        Синхронизация статусов открытых задач пользователя с Яндекс.Трекером.
        Проверяет каждую открытую задачу через API и обновляет статус в БД.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Список ключей задач, которые были закрыты
        """
        open_keys = self.db.get_user_tasks(user_id, status='open')
        closed_keys = []
        
        for task_key in open_keys:
            try:
                issue_data = self.tracker_client.get_issue(task_key)
                if not issue_data:
                    continue
                
                # Статус в Трекере — объект с полем 'key'
                tracker_status = issue_data.get('status', {})
                status_key = tracker_status.get('key', '').lower() if isinstance(tracker_status, dict) else str(tracker_status).lower()
                
                if status_key in COMPLETED_STATUSES:
                    self.db.update_task_status(task_key, 'closed')
                    closed_keys.append(task_key)
                    logger.info(f"🔄 Задача {task_key} закрыта в Трекере (статус: {status_key}), обновлена в БД")
            except Exception as e:
                logger.error(f"❌ Ошибка синхронизации задачи {task_key}: {e}")
        
        return closed_keys
    
    def sync_all_open_tasks(self) -> List[str]:
        """
        Синхронизация статусов ВСЕХ открытых задач в БД с Яндекс.Трекером.
        
        Returns:
            Список ключей задач, которые были закрыты
        """
        all_tasks = self.db.data.get('tasks', {})
        closed_keys = []
        
        for task_key, task_info in all_tasks.items():
            if task_info.get('status') != 'open':
                continue
            
            try:
                issue_data = self.tracker_client.get_issue(task_key)
                if not issue_data:
                    continue
                
                tracker_status = issue_data.get('status', {})
                status_key = tracker_status.get('key', '').lower() if isinstance(tracker_status, dict) else str(tracker_status).lower()
                
                if status_key in COMPLETED_STATUSES:
                    self.db.update_task_status(task_key, 'closed')
                    closed_keys.append(task_key)
                    logger.info(f"🔄 Задача {task_key} закрыта в Трекере (статус: {status_key})")
            except Exception as e:
                logger.error(f"❌ Ошибка синхронизации задачи {task_key}: {e}")
        
        if closed_keys:
            logger.info(f"🔄 Синхронизация завершена: {len(closed_keys)} задач закрыто")
        
        return closed_keys
    
    async def _periodic_sync_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Фоновый job — периодическая синхронизация:
        1. Статусы задач (закрытие)
        2. Назначение исполнителя (уведомление создателю)
        Запускается каждые 5 минут.
        """
        logger.info("🔄 Запуск периодической синхронизации...")
        
        all_tasks = self.db.data.get('tasks', {})
        closed_keys = []
        
        for task_key, task_info in list(all_tasks.items()):
            if task_info.get('status') != 'open':
                continue
            
            try:
                issue_data = self.tracker_client.get_issue(task_key)
                if not issue_data:
                    continue
                
                # --- Проверка статуса ---
                tracker_status = issue_data.get('status', {})
                status_key = tracker_status.get('key', '').lower() if isinstance(tracker_status, dict) else str(tracker_status).lower()
                
                if status_key in COMPLETED_STATUSES:
                    self.db.update_task_status(task_key, 'closed')
                    closed_keys.append(task_key)
                    logger.info(f"🔄 Задача {task_key} закрыта в Трекере (статус: {status_key})")
                
                # --- Проверка назначения исполнителя ---
                assignee_data = issue_data.get('assignee')
                if assignee_data and isinstance(assignee_data, dict):
                    assignee_name = assignee_data.get('display', assignee_data.get('id', ''))
                    last_assignee = task_info.get('last_assignee', '')
                    
                    if assignee_name and assignee_name != last_assignee:
                        # Обновляем в БД
                        self.db.data['tasks'][task_key]['last_assignee'] = assignee_name
                        self.db._save_db()
                        
                        creator_id = task_info.get('creator_id')
                        if creator_id and last_assignee != '':
                            # Уведомляем только если исполнитель ИЗМЕНИЛСЯ (не первое назначение при создании)
                            summary = task_info.get('summary', 'Без названия')
                            task_url = f"https://tracker.yandex.ru/{task_key}"
                            try:
                                await context.bot.send_message(
                                    chat_id=creator_id,
                                    text=(
                                        f"👤 Назначен исполнитель!\n\n"
                                        f"📌 {task_key}\n"
                                        f"📝 {summary}\n"
                                        f"🙋 Исполнитель: {assignee_name}\n"
                                        f"🔗 {task_url}"
                                    )
                                )
                            except Exception as e:
                                logger.error(f"❌ Ошибка уведомления о назначении {task_key}: {e}")
                        elif creator_id and last_assignee == '':
                            # Первое назначение — просто сохраняем без уведомления
                            pass
                
            except Exception as e:
                logger.error(f"❌ Ошибка синхронизации задачи {task_key}: {e}")
        
        # Уведомляем создателей о закрытых задачах
        for task_key in closed_keys:
            task_info = self.db.get_task(task_key)
            if not task_info:
                continue
            
            creator_id = task_info.get('creator_id')
            if not creator_id:
                continue
            
            summary = task_info.get('summary', 'Без названия')
            task_url = f"https://tracker.yandex.ru/{task_key}"
            
            try:
                await context.bot.send_message(
                    chat_id=creator_id,
                    text=(
                        f"✅ Задача закрыта в Трекере!\n\n"
                        f"📌 {task_key}\n"
                        f"📝 {summary}\n"
                        f"🔗 {task_url}\n\n"
                        f"Задача убрана из /mytasks"
                    )
                )
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить пользователя {creator_id} о закрытии {task_key}: {e}")
        
        if closed_keys:
            logger.info(f"🔄 Синхронизация: {len(closed_keys)} задач закрыто")
    
    async def mytasks_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /mytasks — активные задачи текущего пользователя.
        Перед показом синхронизирует статусы с Яндекс.Трекером.
        """
        user_id = update.effective_user.id
        
        # Синхронизируем статусы с Трекером перед показом
        await update.message.reply_text("🔄 Проверяю статусы задач в Трекере...")
        closed_keys = self.sync_user_tasks_status(user_id)
        
        # Получаем активные задачи пользователя (только open)
        active_keys = self.db.get_user_tasks(user_id, status='open')
        
        if not active_keys:
            msg = "📭 У вас нет активных задач.\n\n"
            if closed_keys:
                msg += f"✅ Только что закрыто задач: {len(closed_keys)}\n\n"
            msg += (
                "💡 Создайте задачу, например:\n"
                "#hr Нанять дизайнера"
            )
            await update.message.reply_text(msg)
            return
        
        text = ""
        if closed_keys:
            text += f"✅ Закрыто в Трекере: {len(closed_keys)} задач(и)\n\n"
        
        text += f"📋 Ваши активные задачи ({len(active_keys)}):\n\n"
        
        for idx, task_key in enumerate(active_keys, 1):
            task_info = self.db.get_task(task_key)
            if not task_info:
                continue
            
            task_url = f"https://tracker.yandex.ru/{task_key}"
            summary = task_info.get('summary', 'Без названия')
            queue = task_info.get('queue', '?')
            dept_code = task_info.get('department', '')
            dept_name = DEPARTMENT_MAPPING.get(dept_code, {}).get('name', dept_code or 'Общая')
            created_at = task_info.get('created_at', '')[:10]
            
            text += (
                f"{idx}. 📌 {task_key}\n"
                f"   📝 {summary}\n"
                f"   🏢 {dept_name} ({queue})\n"
                f"   📅 {created_at}\n"
                f"   🔗 {task_url}\n\n"
            )
        
        text += "💡 Закрытые задачи автоматически скрываются."
        
        await update.message.reply_text(text)
    
    async def history_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /history — завершённые задачи пользователя за последнюю неделю.
        """
        user_id = update.effective_user.id
        
        # Получаем все задачи пользователя со статусом closed
        closed_keys = self.db.get_user_tasks(user_id, status='closed')
        
        if not closed_keys:
            await update.message.reply_text(
                "📭 У вас нет завершённых задач за последнюю неделю."
            )
            return
        
        # Фильтруем: только за последнюю неделю
        week_ago = datetime.now() - timedelta(days=7)
        recent_tasks = []
        
        for task_key in closed_keys:
            task_info = self.db.get_task(task_key)
            if not task_info:
                continue
            
            # Проверяем дату обновления или создания
            updated_at = task_info.get('updated_at', task_info.get('created_at', ''))
            if updated_at:
                try:
                    task_date = datetime.fromisoformat(updated_at)
                    if task_date >= week_ago:
                        recent_tasks.append((task_key, task_info))
                except (ValueError, TypeError):
                    pass
        
        if not recent_tasks:
            await update.message.reply_text(
                "📭 У вас нет завершённых задач за последнюю неделю."
            )
            return
        
        text = f"📜 Завершённые задачи за неделю ({len(recent_tasks)}):\n\n"
        
        for idx, (task_key, task_info) in enumerate(recent_tasks, 1):
            task_url = f"https://tracker.yandex.ru/{task_key}"
            summary = task_info.get('summary', 'Без названия')
            queue = task_info.get('queue', '?')
            dept_code = task_info.get('department', '')
            dept_name = DEPARTMENT_MAPPING.get(dept_code, {}).get('name', dept_code or 'Общая')
            updated_at = task_info.get('updated_at', task_info.get('created_at', ''))[:10]
            
            text += (
                f"{idx}. ✅ {task_key}\n"
                f"   📝 {summary}\n"
                f"   🏢 {dept_name} ({queue})\n"
                f"   📅 Закрыта: {updated_at}\n"
                f"   🔗 {task_url}\n\n"
            )
        
        await update.message.reply_text(text)
    
    async def handle_complete_task(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик нажатия кнопки завершения задачи
        
        Args:
            update: Объект обновления Telegram
            context: Контекст бота
        """
        query = update.callback_query
        await query.answer()
        
        logger.info(f"="*60)
        logger.info(f"🔘 НАЖАТА КНОПКА 'Завершить задачу'")
        
        user_id = query.from_user.id
        logger.info(f"👤 Пользователь {user_id} нажал кнопку завершения")
        
        # Извлекаем ключ задачи из callback_data
        callback_data = query.data
        logger.info(f"📥 Получен callback_data: {callback_data}")
        
        if not callback_data.startswith('complete_'):
            logger.warning(f"⚠️ Неверный формат callback_data: {callback_data}")
            return
        
        issue_key = callback_data.replace('complete_', '')
        logger.info(f"🔑 Извлечен issue_key: {issue_key}")
        
        # Получаем информацию о задаче из БД
        task_info = self.db.get_task(issue_key)
        logger.info(f"💾 Задача в БД: {task_info}")
        
        if not task_info:
            logger.error(f"❌ Задача {issue_key} НЕ найдена в БД")
            await query.edit_message_text(
                f"❌ Задача {issue_key} не найдена в базе данных."
            )
            return
        
        # Пытаемся завершить задачу в Трекере
        logger.info(f"🔄 Отправляю запрос на закрытие задачи {issue_key} в Яндекс.Трекер...")
        result = self.tracker_client.update_issue_status(issue_key, 'closed')
        logger.info(f"📤 Результат от Яндекс.Трекер: {result}")
        
        if result:
            logger.info(f"✅ Задача {issue_key} успешно закрыта!")
            # Обновляем статус в БД
            self.db.update_task_status(issue_key, 'closed')
            
            # Обновляем сообщение с кнопкой (для менеджера)
            original_text = query.message.text
            new_text = original_text + f"\n\n✅ Задача {issue_key} завершена!"
            
            await query.edit_message_text(new_text)
            logger.info(f"📝 Сообщение в Telegram обновлено")
            
            # Отправляем уведомление в чат (для всех, включая партнеров)
            summary = task_info.get('summary', 'без названия')
            chat_id = task_info.get('chat_id')
            
            notification_text = f"✅ Задача выполнена!\n\n📝 {summary}"
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=notification_text
                )
                logger.info(f"📤 Уведомление о завершении отправлено в чат {chat_id}")
            except Exception as e:
                logger.error(f"❌ Не удалось отправить уведомление в чат: {e}")
        else:
            logger.error(f"❌ НЕ УДАЛОСЬ закрыть задачу {issue_key}")
            await query.message.reply_text(
                f"❌ Не удалось завершить задачу {issue_key}. "
                "Возможно, статус 'closed' недоступен для этой задачи. "
                "Завершите задачу вручную в Трекере."
            )
        
        logger.info(f"="*60)
    
    async def start_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /start
        """
        user = update.effective_user
        chat_id = update.effective_chat.id
        user_id = user.id
        is_manager = self.is_manager(user_id)
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я бот для создания задач в Яндекс.Трекере.\n\n"
            "📝 Отделы:\n"
            "#hr — HR | #cc — Колл-центр | #razrab — Разработка\n"
            "#owner — Владелец | #buy — Закупки\n"
            "#comm — Коммуникации | #head — Руководство\n\n"
            "Пример: #hr Нанять дизайнера\n\n"
            "📋 Команды:\n"
            "/mytasks — ваши активные задачи\n"
            "/history — завершённые за неделю\n"
            "/help — справка\n"
        )
        
        if is_manager:
            welcome_text += (
                "\n👔 Менеджер:\n"
                f"{TASK_HASHTAG} WEB#ID текст — партнёрская задача\n"
                "/partners — список партнёров\n"
            )
        
        welcome_text += f"\n🆔 Ваш ID: {user_id}"
        
        await update.message.reply_text(welcome_text)
    
    async def help_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /help
        """
        user_id = update.effective_user.id
        is_manager = self.is_manager(user_id)
        
        help_text = "🔧 Команды:\n\n"
        help_text += "/start — начало работы\n"
        help_text += "/help — эта справка\n"
        help_text += "/mytasks — ваши активные задачи\n"
        help_text += "/history — завершённые за неделю\n"
        
        if is_manager:
            help_text += "/partners — список партнёров\n"
            help_text += "/partner WEB2 — задачи партнёра\n"
        
        help_text += "\n📝 Отделы:\n"
        help_text += "#hr — HR | #cc — Колл-центр | #razrab — Разработка\n"
        help_text += "#owner — Владелец | #buy — Закупки\n"
        help_text += "#comm — Коммуникации | #head — Руководство\n"
        
        help_text += (
            "\nПример: #hr Нанять дизайнера\n\n"
            "💡 Как работает:\n"
            "• #отдел + текст → задача в Трекере\n"
            "• Подтверждение + кнопка завершения в ЛС\n"
            "• Ответьте на сообщение бота → комментарий в задаче\n"
            "• Закрытые задачи уходят из /mytasks\n"
        )
        
        if is_manager:
            help_text += (
                f"\n� Партнёрские задачи:\n"
                f"{TASK_HASHTAG} WEB#ID текст задачи\n"
            )
        
        await update.message.reply_text(help_text)
    
    async def partners_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /partners - список всех партнеров
        """
        user_id = update.effective_user.id
        
        # Только менеджеры могут видеть список партнеров
        if not self.is_manager(user_id):
            await update.message.reply_text(
                "❌ Эта команда доступна только менеджерам."
            )
            return
        
        logger.info("🔍 Поиск всех партнерских задач...")
        
        # Получаем все задачи из БД
        all_tasks = self.db.data.get('tasks', {})
        
        # Группируем по партнерам
        partners_tasks = {}
        for task_key, task_info in all_tasks.items():
            queue = task_info.get('queue', '')
            dept = task_info.get('department', '')
            status = task_info.get('status', '')
            
            # Ищем задачи в очереди PARTNERS с открытым статусом
            if queue == PARTNERS_QUEUE and status == 'open':
                # department теперь содержит тег: WEB2, WEB3, WEB5, etc
                partner_tag = dept if dept and dept.startswith('WEB') else None
                
                if partner_tag:
                    if partner_tag not in partners_tasks:
                        partners_tasks[partner_tag] = []
                    partners_tasks[partner_tag].append(task_key)
                    logger.info(f"  ✅ {task_key} → {partner_tag}")
        
        if not partners_tasks:
            await update.message.reply_text(
                "📭 Нет активных партнерских задач.\n\n"
                "💡 Создайте задачу: #задача WEB#2 текст"
            )
            return
        
        partners_text = "📊 Партнеры с активными задачами:\n\n"
        
        for partner_tag in sorted(partners_tasks.keys()):
            count = len(partners_tasks[partner_tag])
            partners_text += f"🔹 {partner_tag}: {count} задач(и)\n"
        
        partners_text += (
            f"\n💡 Всего партнеров: {len(partners_tasks)}\n"
            f"📋 Всего задач: {sum(len(tasks) for tasks in partners_tasks.values())}\n\n"
            "Используйте /partner WEB2 для деталей"
        )
        
        await update.message.reply_text(partners_text)
    
    async def partner_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /partner WEB2 - задачи конкретного партнера
        """
        user_id = update.effective_user.id
        
        # Только менеджеры могут видеть задачи партнеров
        if not self.is_manager(user_id):
            await update.message.reply_text(
                "❌ Эта команда доступна только менеджерам."
            )
            return
        
        # Получаем ID партнера из аргументов
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID партнера.\n"
                "Пример: /partner WEB2 или /partner 2"
            )
            return
        
        partner_input = context.args[0].upper()
        # Убираем WEB# если есть, оставляем только номер
        partner_id = partner_input.replace('WEB', '').replace('#', '')
        partner_tag = f"WEB{partner_id}"
        
        logger.info(f"🔍 Поиск задач партнера {partner_tag}...")
        
        # Получаем все задачи из БД
        all_tasks = self.db.data.get('tasks', {})
        partner_tasks = []
        
        for task_key, task_info in all_tasks.items():
            queue = task_info.get('queue', '')
            dept = task_info.get('department', '')
            status = task_info.get('status', '')
            
            # Проверяем задачи в очереди PARTNERS с нужным тегом
            if queue == PARTNERS_QUEUE and status == 'open' and dept == partner_tag:
                partner_tasks.append((task_key, task_info))
                logger.info(f"  ✅ {task_key} → {partner_tag}")
        
        if not partner_tasks:
            await update.message.reply_text(
                f"📭 У партнера {partner_tag} нет активных задач.\n\n"
                f"💡 Создайте задачу: #задача WEB#{partner_id} текст"
            )
            return
        
        tasks_text = f"📋 Задачи партнера {partner_tag} ({len(partner_tasks)}):\n\n"
        
        for idx, (task_key, task_info) in enumerate(partner_tasks, 1):
            task_url = f"https://tracker.yandex.ru/{task_key}"
            summary = task_info.get('summary', 'Без названия')
            
            tasks_text += (
                f"{idx}. 📌 {task_key}\n"
                f"   📝 {summary}\n"
                f"   🔗 {task_url}\n\n"
            )
        
        await update.message.reply_text(tasks_text)
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("mytasks", self.mytasks_command))
        application.add_handler(CommandHandler("partners", self.partners_command))
        application.add_handler(CommandHandler("partner", self.partner_command))
        application.add_handler(CommandHandler("history", self.history_command))
        
        # Регистрируем обработчик кнопок
        application.add_handler(CallbackQueryHandler(self.handle_complete_task))
        
        # Регистрируем обработчик сообщений
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Фоновая синхронизация статусов задач с Трекером (каждые 5 минут)
        application.job_queue.run_repeating(
            self._periodic_sync_job,
            interval=300,  # 5 минут
            first=60       # первый запуск через 1 минуту
        )
        
        # Запускаем бота
        logger.info("Бот запущен и готов к работе!")
        logger.info(f"Настроено отделов: {len(DEPARTMENT_MAPPING)}")
        logger.info(f"Менеджеров в системе: {len(MANAGER_IDS)}")
        logger.info("🔄 Синхронизация статусов: каждые 5 минут")
        logger.info("Партнеры указывают свой ID в формате WEB#123")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = TrackerBot()
    bot.run()
