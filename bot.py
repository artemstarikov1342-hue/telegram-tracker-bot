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
import requests
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timedelta, timezone
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
    COMPLETED_STATUSES,
    TASK_CLOSER_IDS,
    REPORT_RECIPIENT_IDS,
    OVERDUE_DAYS,
    ASSIGNEE_TELEGRAM_MAP,
    NOTIFY_ALL_TASKS_IDS,
    APPROVAL_STATUS_KEY,
    APPROVAL_NOTIFY_IDS,
    DAILY_REMINDER_TIME,
    MAIN_MANAGER_ID,
    TELEGRAM_TRACKER_MAP
)
from yandex_tracker import YandexTrackerClient
from database import TaskDatabase

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8'),
    ]
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
    
    async def _download_and_attach_photos(self, message, context: ContextTypes.DEFAULT_TYPE, issue_key: str) -> tuple:
        """
        Скачивает фото из сообщения и прикрепляет к задаче в Трекере
        
        Args:
            message: Сообщение Telegram
            context: Контекст бота
            issue_key: Ключ задачи в Трекере
            
        Returns:
            Кортеж (количество фото, список URL фото)
        """
        photos = []
        
        if message.photo:
            photos.append(message.photo[-1])
        
        if message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
            photos.append(message.document)
        
        if not photos:
            return 0, []
        
        count = 0
        photo_urls = []
        for idx, photo in enumerate(photos):
            try:
                file = await context.bot.get_file(photo.file_id)
                file_bytes = await file.download_as_bytearray()
                ts = int(datetime.now().timestamp())
                filename = f"photo_{issue_key}_{ts}_{idx + 1}.jpg"
                result = self.tracker_client.attach_file(issue_key, bytes(file_bytes), filename)
                if result:
                    count += 1
                    # Получаем URL файла из ответа API
                    file_url = result.get('self')
                    if file_url:
                        photo_urls.append(file_url)
                    logger.info(f"📷 ✅ Фото {filename} прикреплено к {issue_key}, URL: {file_url}")
                else:
                    logger.error(f"📷 ❌ Не удалось прикрепить фото к {issue_key}")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки фото к {issue_key}: {e}")
        
        return count, photo_urls
    
    async def handle_reply_comment(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Обработка ответа на сообщение бота — добавление комментария в задачу Трекера.
        Поддерживает текст и фото.
        
        Returns:
            True если это был reply-комментарий и он обработан, False иначе
        """
        if not message.reply_to_message:
            return False
        
        reply_msg = message.reply_to_message
        reply_text = (reply_msg.text or '') + (reply_msg.caption or '')
        
        logger.info(f"📩 Reply обнаружен. from_user: {reply_msg.from_user}, text[:80]: {reply_text[:80]}")
        
        # Ищем ключ задачи в тексте сообщения (формат: QUEUE-123)
        issue_keys = re.findall(r'[A-Z]+-\d+', reply_text)
        logger.info(f"🔍 Найденные ключи задач: {issue_keys}")
        
        if not issue_keys:
            return False
        
        # Берём первый найденный ключ
        issue_key = issue_keys[0]
        comment_text = (message.text or message.caption or '').strip()
        username = message.from_user.username or message.from_user.first_name
        has_photo = bool(message.photo)
        
        if not comment_text and not has_photo:
            return False
        
        # Проверяем, что задача существует в нашей БД
        task_info = self.db.get_task(issue_key)
        if not task_info:
            logger.info(f"⚠️ Задача {issue_key} не найдена в БД, пропускаем reply")
            return False
        
        # Прикрепляем фото если есть
        photo_count = 0
        photo_urls = []
        if has_photo:
            photo_count, photo_urls = await self._download_and_attach_photos(message, context, issue_key)
        
        # Формируем комментарий
        full_comment = f"💬 Комментарий от @{username}:\n\n"
        if comment_text:
            full_comment += comment_text
        if photo_count:
            full_comment += "\n\n**📎 Фото прикреплено (см. вложения)**"
        
        if comment_text or photo_count:
            logger.info(f"📤 Отправляю комментарий к {issue_key}: text={bool(comment_text)}, photos={photo_count}")
            result = self.tracker_client.add_comment(issue_key, full_comment)
        else:
            result = None
        
        # Ответ пользователю
        reply_parts = []
        if result:
            if comment_text:
                reply_parts.append("💬 Комментарий добавлен")
            if photo_count:
                reply_parts.append(f"📎 Фото: {photo_count}")
        
        if reply_parts:
            await message.reply_text(f"{' | '.join(reply_parts)} → {issue_key}")
            logger.info(f"✅ Reply от {username} к {issue_key}: text={bool(comment_text)}, photos={photo_count}")
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
        if not update.message:
            return
        
        message = update.message
        message_text = message.text or message.caption or ''
        
        if not message_text:
            return
        
        # Проверяем reply-комментарий
        if await self.handle_reply_comment(message, context):
            return
        
        message_text = message_text
        user_id = message.from_user.id
        chat_id = message.chat.id
        chat_type = message.chat.type
        username = message.from_user.username or message.from_user.first_name
        
        # Регистрируем пользователя для маппинга username -> user_id
        if message.from_user.username:
            self.db.register_user(user_id, message.from_user.username, message.from_user.first_name)
        
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
        
        # Описание задачи — только текст пользователя
        full_description = description if description else ""
        
        # Список созданных задач
        created_issues = []
        
        # Дедлайн
        deadline = self.get_deadline_date()
        
        # Определяем логин автора в Трекере для добавления как наблюдателя
        author_tracker_login = None
        tg_username = message.from_user.username
        if tg_username:
            for tg_name, tr_login in TELEGRAM_TRACKER_MAP.items():
                if tg_name.lower() == tg_username.lower():
                    author_tracker_login = tr_login
                    break
        followers = [author_tracker_login] if author_tracker_login else None
        
        # Создаем задачи в указанных отделах
        logger.info(f"🚀 Начинаем создание задач...")
        for dept_code in departments:
            dept_info = DEPARTMENT_MAPPING[dept_code]
            queue = dept_info['queue']
            logger.info(f"  → Создаём задачу в очереди {queue} (отдел: {dept_info['name']})")
            
            # Объединяем наблюдателей: из конфига отдела + автор
            dept_followers = list(dept_info.get('followers', []))
            if author_tracker_login and author_tracker_login not in dept_followers:
                dept_followers.append(author_tracker_login)
            
            issue = self.tracker_client.create_issue(
                queue=queue,
                summary=summary,
                description=full_description,
                assignee=dept_info.get('assignee'),
                priority=DEFAULT_PRIORITY,
                deadline=deadline,
                tags=['telegram', dept_code, f'chat_{chat_id}'],
                followers=dept_followers or None
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
                description=full_description,
                assignee=assignee,
                priority=DEFAULT_PRIORITY,
                deadline=deadline,
                tags=['telegram', 'partner', partner_tag, f'chat_{chat_id}'],
                followers=followers
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
                tags=['telegram', f'chat_{chat_id}'],
                followers=followers
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
            # Уведомляем NOTIFY_ALL_TASKS_IDS (партнёрские задачи)
            for notify_id in NOTIFY_ALL_TASKS_IDS:
                if notify_id == user_id:
                    continue
                try:
                    await context.bot.send_message(
                        chat_id=notify_id,
                        text=f"📬 Партнёрская задача!\n\n{manager_message}",
                        reply_markup=reply_markup
                    )
                    logger.info(f"📬 Уведомление о партнёрской задаче → {notify_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка уведомления {notify_id}: {e}")
        else:
            err = self.tracker_client.last_error or 'Неизвестная ошибка'
            await message.reply_text(
                f"❌ Ошибка при создании задачи в Яндекс.Трекере.\n"
                f"⚠️ Причина: {err}"
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
        
        # Описание задачи — только текст пользователя
        full_description = description if description else ""
        
        deadline = self.get_deadline_date()
        
        # Определяем логин автора в Трекере для добавления как наблюдателя
        author_tracker_login = None
        tg_username = message.from_user.username
        if tg_username:
            for tg_name, tr_login in TELEGRAM_TRACKER_MAP.items():
                if tg_name.lower() == tg_username.lower():
                    author_tracker_login = tr_login
                    break
        
        # Объединяем наблюдателей: автор + из конфига отдела
        followers = list(dept_info.get('followers', []))
        if author_tracker_login and author_tracker_login not in followers:
            followers.append(author_tracker_login)
        followers = followers or None
        
        # Создаём задачу в Трекере
        logger.info(f"🚀 Создаём задачу в очереди {queue} ({dept_name})")
        issue = self.tracker_client.create_issue(
            queue=queue,
            summary=summary,
            description=full_description,
            assignee=dept_info.get('assignee'),
            priority=DEFAULT_PRIORITY,
            deadline=deadline,
            tags=['telegram', dept_code, f'user_{user_id}', f'chat_{chat_id}'],
            followers=followers
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
            
            # Прикрепляем фото как вложение
            photo_count = 0
            photo_urls = []
            has_photo = bool(message.photo)
            has_doc_img = bool(message.document and message.document.mime_type and message.document.mime_type.startswith('image/'))
            logger.info(f"📷 Проверка фото для {issue_key}: photo={has_photo}, doc_img={has_doc_img}")
            if has_photo or has_doc_img:
                photo_count, photo_urls = await self._download_and_attach_photos(message, context, issue_key)
                if photo_count:
                    # Добавляем пометку в описание
                    new_description = full_description
                    if new_description:
                        new_description += "\n\n"
                    new_description += "**📎 Фото прикреплено (см. вложения)**"
                    self.tracker_client.update_issue(issue_key, description=new_description)
                    logger.info(f"📎 Прикреплено {photo_count} фото к {issue_key}")
            
            # Сообщение в группу (с ключом задачи для reply-комментариев, без кнопки завершения)
            if chat_type in ('group', 'supergroup'):
                assignee_login = dept_info.get('assignee') or ''
                tg_username = ASSIGNEE_TELEGRAM_MAP.get(assignee_login, '')
                assignee_text = f'@{tg_username}' if tg_username else (assignee_login or 'не назначен')
                
                group_msg = (
                    f"✅ Задача создана\n\n"
                    f"📝 {summary}\n"
                    f"🏢 Отдел: {dept_name}\n"
                )
                if photo_count:
                    group_msg += f"📎 Фото: {photo_count}\n"
                group_msg += (
                    f"📋 {issue_key}\n"
                    f"🔗 {issue_url}\n\n"
                    f"💬 Ответьте на это сообщение, чтобы добавить комментарий"
                )
                await message.reply_text(group_msg)
            
            # Полное сообщение в ЛС создателю
            dm_message = (
                f"✅ Задача создана успешно!\n\n"
                f"📝 Название: {summary}\n"
                f"🏢 Отдел: {dept_name} ({queue})\n"
                f"⚠️ Приоритет: {DEFAULT_PRIORITY}\n"
                f"📅 Дедлайн: {deadline}\n"
            )
            if photo_count:
                dm_message += f"📎 Фото: {photo_count}\n"
            dm_message += (
                f"\n📋 {issue_key}\n"
                f"🔗 {issue_url}"
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
                dm_sent = await context.bot.send_message(
                    chat_id=user_id,
                    text=dm_message,
                    reply_markup=reply_markup
                )
                # Сохраняем ID сообщения с кнопкой для автозакрытия
                self.db.data['tasks'][issue_key]['dm_chat_id'] = user_id
                self.db.data['tasks'][issue_key]['dm_message_id'] = dm_sent.message_id
                self.db._save_db()
                logger.info(f"✅ Отправлено ЛС пользователю {user_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ЛС: {e}")
                # Если ЛС не удалось — отправляем в текущий чат
                await message.reply_text(
                    dm_message,
                    reply_markup=reply_markup
                )
            # Уведомляем NOTIFY_ALL_TASKS_IDS (все задачи без исключений)
            for notify_id in NOTIFY_ALL_TASKS_IDS:
                if notify_id == user_id:
                    continue  # Уже отправили создателю
                try:
                    notify_msg = (
                        f"📬 Новая задача!\n\n"
                        f"📝 {summary}\n"
                        f"🏢 Отдел: {dept_name} ({queue})\n"
                        f"👤 Автор: @{username}\n"
                        f"🙋 Исполнитель: {dept_info.get('assignee') or 'не назначен'}\n"
                    )
                    if photo_count:
                        notify_msg += f"📎 Фото: {photo_count}\n"
                    notify_msg += (
                        f"\n📋 {issue_key}\n"
                        f"🔗 {issue_url}"
                    )
                    await context.bot.send_message(
                        chat_id=notify_id,
                        text=notify_msg,
                        reply_markup=reply_markup
                    )
                    logger.info(f"📬 Уведомление о задаче {issue_key} → {notify_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка уведомления {notify_id}: {e}")
        else:
            err = self.tracker_client.last_error or 'Неизвестная ошибка'
            await message.reply_text(
                f"❌ Ошибка при создании задачи в Яндекс.Трекере.\n"
                f"⚠️ Причина: {err}"
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
        3. Напоминания исполнителям в личку
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
                
                # --- Проверка перехода в "Согласование результата" ---
                last_status = task_info.get('last_status_key', '')
                if status_key == APPROVAL_STATUS_KEY.lower() and last_status != APPROVAL_STATUS_KEY.lower():
                    summary = task_info.get('summary', 'Без названия')
                    task_url = f"https://tracker.yandex.ru/{task_key}"
                    dept = task_info.get('department', '')
                    dept_name = DEPARTMENT_MAPPING.get(dept, {}).get('name', dept)
                    
                    for notify_id in APPROVAL_NOTIFY_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=notify_id,
                                text=(
                                    f"🔔 Задача требует согласования!\n\n"
                                    f"📌 {task_key}\n"
                                    f"📝 {summary}\n"
                                    f"🏢 Отдел: {dept_name}\n"
                                    f"📊 Статус: Согласование результата\n\n"
                                    f"🔗 {task_url}"
                                ),
                                reply_markup=InlineKeyboardMarkup([[
                                    InlineKeyboardButton("↗️ Открыть в Tracker", url=task_url)
                                ]])
                            )
                            logger.info(f"🔔 Уведомление о согласовании {task_key} → {notify_id}")
                        except Exception as e:
                            logger.error(f"❌ Ошибка уведомления о согласовании {task_key}: {e}")
                
                # Сохраняем текущий статус
                if status_key != last_status:
                    self.db.data['tasks'][task_key]['last_status_key'] = status_key
                    self.db._save_db()
                
                # --- Проверка назначения исполнителя ---
                assignee_data = issue_data.get('assignee')
                if assignee_data and isinstance(assignee_data, dict):
                    assignee_login = assignee_data.get('login', '')
                    assignee_name = assignee_data.get('display', assignee_login)
                    last_assignee = task_info.get('last_assignee', '')
                    
                    if assignee_name and assignee_name != last_assignee:
                        # Обновляем в БД
                        self.db.data['tasks'][task_key]['last_assignee'] = assignee_name
                        self.db._save_db()
                        
                        summary = task_info.get('summary', 'Без названия')
                        creator_id = task_info.get('creator_id')
                        if creator_id and last_assignee != '':
                            # Уведомляем только если исполнитель ИЗМЕНИЛСЯ (не первое назначение при создании)
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
                            # Первое назначение — отправляем напоминание исполнителю
                            await self._notify_assignee(context, task_key, assignee_login, summary)
                
                # --- Проверка новых комментариев ---
                comments = self.tracker_client.get_comments(task_key)
                if comments:
                    last_comment_count = task_info.get('last_comment_count', 0)
                    current_count = len(comments)
                    
                    if current_count > last_comment_count:
                        # Есть новые комментарии
                        new_comments = comments[last_comment_count:]
                        creator_id = task_info.get('creator_id')
                        
                        for comment in new_comments:
                            author = comment.get('createdBy', {})
                            author_display = author.get('display', 'Неизвестный') if isinstance(author, dict) else str(author)
                            comment_text = comment.get('text', '')[:200]
                            
                            # Не уведомляем о своих же комментариях (от бота через Telegram)
                            if '💬 Комментарий от @' in comment_text:
                                continue
                            
                            if creator_id and comment_text:
                                summary = task_info.get('summary', 'Без названия')
                                task_url = f"https://tracker.yandex.ru/{task_key}"
                                try:
                                    await context.bot.send_message(
                                        chat_id=creator_id,
                                        text=(
                                            f"💬 Новый комментарий в задаче!\n\n"
                                            f"📌 {task_key}\n"
                                            f"📝 {summary}\n"
                                            f"👤 {author_display}:\n"
                                            f"«{comment_text}»\n\n"
                                            f"🔗 {task_url}"
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"❌ Ошибка уведомления о комментарии {task_key}: {e}")
                        
                        self.db.data['tasks'][task_key]['last_comment_count'] = current_count
                        self.db._save_db()
                
            except Exception as e:
                logger.error(f"❌ Ошибка синхронизации задачи {task_key}: {e}")
        
        # Уведомляем создателей о закрытых задачах + убираем кнопку
        for task_key in closed_keys:
            task_info = self.db.get_task(task_key)
            if not task_info:
                continue
            
            creator_id = task_info.get('creator_id')
            if not creator_id:
                continue
            
            summary = task_info.get('summary', 'Без названия')
            task_url = f"https://tracker.yandex.ru/{task_key}"
            
            # Убираем кнопку "Завершить" из ЛС (автозакрытие)
            dm_chat_id = task_info.get('dm_chat_id')
            dm_message_id = task_info.get('dm_message_id')
            if dm_chat_id and dm_message_id:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=dm_chat_id,
                        message_id=dm_message_id,
                        reply_markup=None
                    )
                    logger.info(f"🔘 Кнопка убрана из ЛС для {task_key}")
                except Exception as e:
                    logger.error(f"⚠️ Не удалось убрать кнопку для {task_key}: {e}")
            
            try:
                await context.bot.send_message(
                    chat_id=creator_id,
                    text=(
                        f"✅ Задача закрыта в Трекере!\n\n"
                        f"📌 {task_key}\n"
                        f"📝 {summary}\n"
                        f"🔗 {task_url}"
                    )
                )
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить пользователя {creator_id} о закрытии {task_key}: {e}")
        
        if closed_keys:
            logger.info(f"🔄 Синхронизация: {len(closed_keys)} задач закрыто")
        
        # --- Напоминания о просроченных задачах (>N дней) ---
        now = datetime.now()
        for task_key, task_info in list(all_tasks.items()):
            if task_info.get('status') != 'open':
                continue
            
            created_at_str = task_info.get('created_at', '')
            if not created_at_str:
                continue
            
            try:
                created_at = datetime.fromisoformat(created_at_str)
                days_open = (now - created_at).days
                
                if days_open >= OVERDUE_DAYS:
                    creator_id = task_info.get('creator_id')
                    last_reminder = task_info.get('last_overdue_reminder', '')
                    
                    # Напоминаем максимум раз в день
                    if last_reminder == now.strftime('%Y-%m-%d'):
                        continue
                    
                    summary = task_info.get('summary', 'Без названия')
                    task_url = f"https://tracker.yandex.ru/{task_key}"
                    for manager_id in MANAGER_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=manager_id,
                                text=(
                                    f"⏰ Задача открыта уже {days_open} дн.!\n\n"
                                    f"📌 {task_key}\n"
                                    f"📝 {summary}\n"
                                    f"🔗 {task_url}"
                                )
                            )
                        except Exception as e:
                            logger.error(f"❌ Ошибка напоминания о просрочке {task_key} для {manager_id}: {e}")
                    self.db.data['tasks'][task_key]['last_overdue_reminder'] = now.strftime('%Y-%m-%d')
                    self.db._save_db()
            except Exception:
                continue
    
    async def _notify_assignee(self, context: ContextTypes.DEFAULT_TYPE, task_key: str, assignee_login: str, summary: str) -> None:
        """
        Отправляет напоминание исполнителю в личку
        
        Args:
            context: Контекст бота
            task_key: Ключ задачи
            assignee_login: Логин исполнителя в Трекере
            summary: Название задачи
        """
        assignee_telegram_id = self._get_telegram_id_by_tracker_login(assignee_login)
        
        if not assignee_telegram_id:
            logger.warning(f"⚠️ Не найден Telegram ID для исполнителя {assignee_login}")
            return
        
        task_url = f"https://tracker.yandex.ru/{task_key}"
        
        try:
            await context.bot.send_message(
                chat_id=assignee_telegram_id,
                text=(
                    f"🔔 Вам назначена задача!\n\n"
                    f"📌 {task_key}\n"
                    f"📝 {summary}\n"
                    f"🙋 Исполнитель: {assignee_login}\n"
                    f"🔗 {task_url}\n\n"
                    f"💬 Ответьте на сообщение бота для комментариев"
                )
            )
            logger.info(f"📬 Напоминание исполнителю {assignee_login} → {assignee_telegram_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминания исполнителю {assignee_login}: {e}")
    
    async def _daily_reminder_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Ежедневные напоминания о всех открытых задачах в 9:55 МСК.
        Отправляет создателям их открытые задачи с пометкой просроченных.
        """
        logger.info("📅 Запуск ежедневных напоминаний...")
        
        now = datetime.now()
        all_tasks = self.db.data.get('tasks', {})
        
        # Группируем открытые задачи по создателям
        user_tasks = {}
        
        for task_key, task_info in all_tasks.items():
            if task_info.get('status') != 'open':
                continue
            
            creator_id = task_info.get('creator_id')
            if not creator_id:
                continue
            
            if creator_id not in user_tasks:
                user_tasks[creator_id] = []
            
            # Определяем статус задачи (просроченная или в работе)
            created_at_str = task_info.get('created_at', '')
            days_open = 0
            is_overdue = False
            
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    days_open = (now - created_at).days
                    is_overdue = days_open >= OVERDUE_DAYS
                except Exception:
                    pass
            
            user_tasks[creator_id].append({
                'key': task_key,
                'summary': task_info.get('summary', 'Без названия'),
                'queue': task_info.get('queue', '?'),
                'department': task_info.get('department', ''),
                'days_open': days_open,
                'is_overdue': is_overdue
            })
        
        # Отправляем напоминания только менеджерам
        manager_all_tasks = {}
        for creator_id, tasks in user_tasks.items():
            for manager_id in MANAGER_IDS:
                if manager_id not in manager_all_tasks:
                    manager_all_tasks[manager_id] = []
                manager_all_tasks[manager_id].extend(tasks)
        
        for manager_id, tasks in manager_all_tasks.items():
            if not tasks:
                continue
            
            # Убираем дубликаты задач
            seen = set()
            unique_tasks = []
            for t in tasks:
                if t['key'] not in seen:
                    seen.add(t['key'])
                    unique_tasks.append(t)
            tasks = unique_tasks
            
            # Сортируем: сначала просроченные
            tasks.sort(key=lambda x: (not x['is_overdue'], x['days_open']))
            
            overdue_count = sum(1 for t in tasks if t['is_overdue'])
            active_count = len(tasks) - overdue_count
            
            text = f"📅 Ежедневное напоминание\n\n"
            text += f"📝 Открытых задач: {len(tasks)} ({overdue_count} просроченных)\n\n"
            
            for idx, task in enumerate(tasks, 1):
                dept_code = task['department']
                dept_name = DEPARTMENT_MAPPING.get(dept_code, {}).get('name', dept_code or 'Общая')
                task_url = f"https://tracker.yandex.ru/{task['key']}"
                
                status_icon = "⏰" if task['is_overdue'] else "📋"
                days_text = f" ({task['days_open']} дн.)" if task['days_open'] > 0 else ""
                
                text += (
                    f"{idx}. {status_icon} {task['key']}{days_text}\n"
                    f"   📝 {task['summary']}\n"
                    f"   🏢 {dept_name} ({task['queue']})\n"
                    f"   🔗 {task_url}\n\n"
                )
            
            try:
                await context.bot.send_message(chat_id=manager_id, text=text)
                logger.info(f"📅 Ежедневное напоминание отправлено менеджеру {manager_id}: {len(tasks)} задач")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ежедневного напоминания {manager_id}: {e}")
        
        logger.info(f"📅 Ежедневные напоминания завершены: {len(manager_all_tasks)} менеджеров")
    
    async def _assignee_reminder_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Напоминания ТОЛЬКО исполнителям о их открытых задачах.
        Запускается в 10:00 МСК ежедневно.
        """
        logger.info("📬 Запуск напоминаний исполнителям...")
        
        # Получаем все открытые задачи из Трекера
        issues = self.tracker_client.get_all_open_issues()
        if not issues:
            logger.info("📭 Нет открытых задач для напоминаний")
            return
        
        # Группируем задачи по исполнителям (БЕЗ наблюдателей)
        user_tasks = {}  # {telegram_id: [tasks]}
        
        for issue in issues:
            issue_key = issue.get('key', '?')
            summary = issue.get('summary', 'Без названия')
            
            # Получаем ТОЛЬКО исполнителя
            assignee_data = issue.get('assignee')
            if assignee_data:
                assignee_login = assignee_data.get('login') if isinstance(assignee_data, dict) else str(assignee_data)
                assignee_telegram_id = self._get_telegram_id_by_tracker_login(assignee_login)
                
                if assignee_telegram_id:
                    if assignee_telegram_id not in user_tasks:
                        user_tasks[assignee_telegram_id] = []
                    user_tasks[assignee_telegram_id].append({
                        'key': issue_key,
                        'summary': summary
                    })
        
        # Отправляем напоминания
        for telegram_id, tasks in user_tasks.items():
            if not tasks:
                continue
            
            text = f"📬 Напоминание о ваших задачах ({len(tasks)})\n\n"
            
            for idx, task in enumerate(tasks, 1):
                task_url = f"https://tracker.yandex.ru/{task['key']}"
                
                text += (
                    f"{idx}. 👤 {task['key']}\n"
                    f"   📝 {task['summary']}\n"
                    f"   🔗 {task_url}\n\n"
                )
            
            try:
                await context.bot.send_message(chat_id=telegram_id, text=text)
                logger.info(f"📬 Напоминание отправлено исполнителю {telegram_id}: {len(tasks)} задач")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки напоминания {telegram_id}: {e}")
        
        logger.info(f"📬 Напоминания завершены: {len(user_tasks)} исполнителей")
    
    async def _overdue_reminder_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Напоминания о просроченных задачах (дедлайн истёк >1 дня).
        Запускается в 9:30 и 15:30 МСК.
        """
        logger.info("⏰ Запуск напоминаний о просроченных задачах...")
        
        # Получаем все открытые задачи из Трекера
        issues = self.tracker_client.get_all_open_issues()
        if not issues:
            logger.info("📭 Нет открытых задач")
            return
        
        now = datetime.now()
        user_overdue_tasks = {}  # {telegram_id: [tasks]}
        
        for issue in issues:
            # Проверяем дедлайн
            deadline_str = issue.get('deadline')
            if not deadline_str:
                continue
            
            try:
                # Парсим дедлайн (формат YYYY-MM-DD)
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
                days_overdue = (now - deadline).days
                
                # Просрочено более 1 дня
                if days_overdue <= 1:
                    continue
                
            except Exception as e:
                logger.error(f"Ошибка парсинга дедлайна для {issue.get('key')}: {e}")
                continue
            
            issue_key = issue.get('key', '?')
            summary = issue.get('summary', 'Без названия')
            
            # Получаем исполнителя
            assignee_data = issue.get('assignee')
            if assignee_data:
                assignee_login = assignee_data.get('login') if isinstance(assignee_data, dict) else str(assignee_data)
                assignee_telegram_id = self._get_telegram_id_by_tracker_login(assignee_login)
                
                if assignee_telegram_id:
                    if assignee_telegram_id not in user_overdue_tasks:
                        user_overdue_tasks[assignee_telegram_id] = []
                    user_overdue_tasks[assignee_telegram_id].append({
                        'key': issue_key,
                        'summary': summary,
                        'days_overdue': days_overdue,
                        'role': 'исполнитель'
                    })
            
            # Получаем наблюдателей
            followers = issue.get('followers', [])
            for follower in followers:
                follower_login = follower.get('login') if isinstance(follower, dict) else str(follower)
                follower_telegram_id = self._get_telegram_id_by_tracker_login(follower_login)
                
                if follower_telegram_id:
                    if follower_telegram_id not in user_overdue_tasks:
                        user_overdue_tasks[follower_telegram_id] = []
                    # Проверяем что не дублируем
                    if not any(t['key'] == issue_key for t in user_overdue_tasks[follower_telegram_id]):
                        user_overdue_tasks[follower_telegram_id].append({
                            'key': issue_key,
                            'summary': summary,
                            'days_overdue': days_overdue,
                            'role': 'наблюдатель'
                        })
        
        # Отправляем напоминания о просрочках
        for telegram_id, tasks in user_overdue_tasks.items():
            if not tasks:
                continue
            
            text = f"⏰ ПРОСРОЧЕННЫЕ ЗАДАЧИ ({len(tasks)})\n\n"
            
            for idx, task in enumerate(tasks, 1):
                task_url = f"https://tracker.yandex.ru/{task['key']}"
                role_icon = "👤" if task['role'] == 'исполнитель' else "👁"
                
                text += (
                    f"{idx}. {role_icon} {task['key']}\n"
                    f"   📝 {task['summary']}\n"
                    f"   ⚠️ Просрочено на {task['days_overdue']} дн.\n"
                    f"   🔗 {task_url}\n\n"
                )
            
            try:
                await context.bot.send_message(chat_id=telegram_id, text=text)
                logger.info(f"⏰ Напоминание о просрочках отправлено {telegram_id}: {len(tasks)} задач")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки напоминания о просрочках {telegram_id}: {e}")
        
        logger.info(f"⏰ Напоминания о просрочках завершены: {len(user_overdue_tasks)} пользователей")
    
    async def _weekly_report_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Еженедельный отчёт — отправляется по понедельникам.
        Сводка: создано/закрыто за неделю, по отделам.
        """
        logger.info("📊 Формирование еженедельного отчёта...")
        
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        all_tasks = self.db.data.get('tasks', {})
        
        created_count = 0
        closed_count = 0
        dept_stats = {}
        
        for task_key, task_info in all_tasks.items():
            dept = task_info.get('department', 'other')
            dept_name = DEPARTMENT_MAPPING.get(dept, {}).get('name', dept)
            
            if dept_name not in dept_stats:
                dept_stats[dept_name] = {'created': 0, 'closed': 0}
            
            created_at_str = task_info.get('created_at', '')
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at >= week_ago:
                        created_count += 1
                        dept_stats[dept_name]['created'] += 1
                except Exception:
                    pass
            
            updated_at_str = task_info.get('updated_at', '')
            if task_info.get('status') == 'closed' and updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                    if updated_at >= week_ago:
                        closed_count += 1
                        dept_stats[dept_name]['closed'] += 1
                except Exception:
                    pass
        
        report = (
            f"📊 Еженедельный отчёт\n"
            f"📅 {week_ago.strftime('%d.%m')} — {now.strftime('%d.%m.%Y')}\n\n"
            f"📝 Создано задач: {created_count}\n"
            f"✅ Закрыто задач: {closed_count}\n\n"
            f"📋 По отделам:\n"
        )
        
        for dept_name, stats in sorted(dept_stats.items()):
            if stats['created'] > 0 or stats['closed'] > 0:
                report += f"  {dept_name}: +{stats['created']} / ✅{stats['closed']}\n"
        
        if not dept_stats:
            report += "  Нет данных за эту неделю\n"
        
        for recipient_id in [MAIN_MANAGER_ID]:  # Только главному менеджеру
            try:
                await context.bot.send_message(chat_id=recipient_id, text=report)
                logger.info(f"📊 Отчёт отправлен главному менеджеру {recipient_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки отчёта {recipient_id}: {e}")
    
    async def _daily_meeting_reminder_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Ежедневное напоминание о дейли митинге в 9:55 МСК.
        Отправляет приглашение на Telemost указанным пользователям.
        """
        logger.info("📞 Отправка приглашения на дейли митинг...")
        
        # Список username участников дейли митинга
        daily_participants = [
            'andy_jobennn_92',
            'quarterbackk',
            'lerpona',
            'n_kotovski',
            'artGHAds'
        ]
        
        meeting_url = "https://telemost.yandex.ru/j/55791300796342"
        
        message = (
            "☀️ Доброе утро!\n\n"
            "📞 Напоминание о дейли митинге\n"
            f"🔗 {meeting_url}\n\n"
            "Присоединяйтесь!"
        )
        
        # Отправляем приглашение каждому участнику
        for username in daily_participants:
            telegram_id = self.db.get_telegram_id_by_username(username)
            
            if telegram_id:
                try:
                    await context.bot.send_message(chat_id=telegram_id, text=message)
                    logger.info(f"📞 Приглашение отправлено @{username} ({telegram_id})")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки приглашения @{username}: {e}")
            else:
                logger.warning(f"⚠️ Не найден Telegram ID для @{username}")
        
        logger.info(f"📞 Приглашения на дейли митинг отправлены: {len(daily_participants)} участников")
    
    def _get_tracker_login_by_telegram(self, user) -> Optional[str]:
        """
        Находит логин Трекера по Telegram username через ASSIGNEE_TELEGRAM_MAP.
        """
        tg_username = user.username
        if not tg_username:
            return None
        tg_username_lower = tg_username.lower()
        for tracker_login, tg_name in ASSIGNEE_TELEGRAM_MAP.items():
            if tg_name.lower() == tg_username_lower:
                return tracker_login
        return None
    
    def _get_telegram_id_by_tracker_login(self, tracker_login: str) -> Optional[int]:
        """
        Находит Telegram ID по логину Трекера через ASSIGNEE_TELEGRAM_MAP и БД пользователей.
        """
        tg_username = ASSIGNEE_TELEGRAM_MAP.get(tracker_login)
        if not tg_username:
            return None
        
        # Ищем user_id в БД по username
        return self.db.get_telegram_id_by_username(tg_username)
    
    async def mytasks_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /mytasks — все задачи создателя из Трекера.
        Загружает напрямую из Трекера по логину пользователя.
        """
        user = update.effective_user
        
        # Получаем логин Трекера по Telegram username (case-insensitive)
        tracker_login = None
        if user.username:
            for tg_name, tr_login in TELEGRAM_TRACKER_MAP.items():
                if tg_name.lower() == user.username.lower():
                    tracker_login = tr_login
                    break
        
        if not tracker_login:
            await update.message.reply_text(
                "❌ Ваш Telegram не привязан к логину Трекера.\n"
                "Обратитесь к менеджеру для настройки.\n\n"
                "💡 Ваш username: @" + (user.username or "не указан")
            )
            return
        
        await update.message.reply_text(f"� Загружаю задачи из Трекера для {tracker_login}...")
        
        # Ищем задачи через Tracker API по создателю
        try:
            issues = self.tracker_client.get_issues_by_creator(tracker_login)
            
            if not issues:
                await update.message.reply_text(
                    f"📭 У вас нет открытых задач в Трекере ({tracker_login}).\n\n"
                    f"📋 Назначенные на вас: /assigned"
                )
                return
            
            text = f"📋 Ваши активные задачи в Трекере:\n\n"
            
            active_issues = []
            for issue in issues:
                status_data = issue.get('status', {})
                status_key = status_data.get('key', '').lower() if isinstance(status_data, dict) else str(status_data).lower()
                if status_key not in COMPLETED_STATUSES:
                    active_issues.append(issue)
            
            if not active_issues:
                await update.message.reply_text(
                    f"📭 У вас нет активных задач в Трекере ({tracker_login}).\n\n"
                    f"📋 Назначенные на вас: /assigned"
                )
                return
            
            for idx, issue in enumerate(active_issues, 1):
                issue_key = issue.get('key', '?')
                summary = issue.get('summary', 'Без названия')
                queue_data = issue.get('queue', {})
                queue_name = queue_data.get('display', queue_data.get('key', '?')) if isinstance(queue_data, dict) else str(queue_data)
                status_data = issue.get('status', {})
                status_name = status_data.get('display', '?') if isinstance(status_data, dict) else str(status_data)
                status_key = status_data.get('key', '').lower() if isinstance(status_data, dict) else str(status_data).lower()
                
                # Определяем иконку для активных задач
                if status_key in ['inprogress', 'в работе']:
                    status_icon = "🔄"
                else:
                    status_icon = "📋"
                
                task_url = f"https://tracker.yandex.ru/{issue_key}"
                
                text += (
                    f"{idx}. {status_icon} {issue_key}\n"
                    f"   📝 {summary}\n"
                    f"   🏢 {queue_name} | {status_name}\n"
                    f"   🔗 {task_url}\n\n"
                )
            
            text += "💡 Назначенные на вас: /assigned"
            
            await update.message.reply_text(text)
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска задач для {tracker_login}: {e}")
            await update.message.reply_text("❌ Ошибка при загрузке задач из Трекера.")
    
    async def assigned_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /assigned — задачи, где пользователь является ИСПОЛНИТЕЛЕМ.
        Ищет по всем очередям через Tracker API.
        """
        user = update.effective_user
        tracker_login = self._get_tracker_login_by_telegram(user)
        
        if not tracker_login:
            await update.message.reply_text(
                "❌ Ваш Telegram не привязан к логину Трекера.\n"
                "Обратитесь к менеджеру для настройки."
            )
            return
        
        await update.message.reply_text("🔄 Загружаю ваши задачи из Трекера...")
        
        # Ищем задачи через Tracker API по assignee
        try:
            url = f'{self.tracker_client.BASE_URL}/issues/_search'
            payload = {
                'filter': {
                    'assignee': tracker_login,
                    'resolution': 'empty()'
                }
            }
            response = requests.post(
                url,
                json=payload,
                headers=self.tracker_client.headers,
                timeout=15
            )
            response.raise_for_status()
            issues = response.json()
        except Exception as e:
            logger.error(f"❌ Ошибка поиска задач для {tracker_login}: {e}")
            await update.message.reply_text("❌ Ошибка при загрузке задач из Трекера.")
            return
        
        if not issues:
            await update.message.reply_text(
                f"📭 На вас нет открытых задач ({tracker_login}).\n\n"
                f"📋 Созданные вами: /mytasks"
            )
            return
        
        text = f"📋 Назначенные на вас задачи ({len(issues)}):\n\n"
        
        for idx, issue in enumerate(issues, 1):
            issue_key = issue.get('key', '?')
            summary = issue.get('summary', 'Без названия')
            queue_data = issue.get('queue', {})
            queue_name = queue_data.get('display', queue_data.get('key', '?')) if isinstance(queue_data, dict) else str(queue_data)
            status_data = issue.get('status', {})
            status_name = status_data.get('display', '?') if isinstance(status_data, dict) else str(status_data)
            task_url = f"https://tracker.yandex.ru/{issue_key}"
            
            text += (
                f"{idx}. 📌 {issue_key}\n"
                f"   📝 {summary}\n"
                f"   🏢 {queue_name} | {status_name}\n"
                f"   🔗 {task_url}\n\n"
            )
        
        text += "📋 Созданные вами: /mytasks"
        
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
        chat_type = query.message.chat.type
        logger.info(f"👤 Пользователь {user_id} нажал кнопку завершения (chat_type: {chat_type})")
        
        # Проверяем, что завершение только в ЛС
        if chat_type != 'private':
            await query.answer("❌ Завершать задачи можно только в ЛС с ботом.", show_alert=True)
            return
        
        # Проверяем права на завершение
        if user_id not in TASK_CLOSER_IDS:
            await query.answer("❌ У вас нет прав на завершение задач.", show_alert=True)
            logger.warning(f"⚠️ Пользователь {user_id} попытался завершить задачу без прав")
            return
        
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
            "/mytasks — созданные вами задачи\n"
            "/assigned — назначенные на вас\n"
            "/move — переместить задачу\n"
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
        help_text += "/mytasks — созданные вами задачи\n"
        help_text += "/assigned — назначенные на вас\n"
        help_text += "/move TASK dept — переместить задачу\n"
        
        help_text += "\n📝 Отделы:\n"
        help_text += "#hr — HR | #cc — Колл-центр | #razrab — Разработка\n"
        help_text += "#owner — Владелец | #buy — Закупки\n"
        help_text += "#comm — Коммуникации | #head — Руководство\n"
        
        help_text += "\nПример: #hr Нанять дизайнера\n"
        
        if is_manager:
            help_text += (
                f"\n👔 Партнёрские задачи:\n"
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
    
    async def assign_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /assign TASK-KEY login — смена исполнителя.
        Пример: /assign HR-5 phozik
        """
        user_id = update.effective_user.id
        
        if user_id not in TASK_CLOSER_IDS and not self.is_manager(user_id):
            await update.message.reply_text("❌ У вас нет прав на смену исполнителя.")
            return
        
        if not context.args or len(context.args) < 2:
            # Формируем подсказки с логинами по отделам
            hints = "📋 Логины исполнителей по отделам:\n\n"
            for dept_code, dept_info in DEPARTMENT_MAPPING.items():
                assignee = dept_info.get('assignee', '')
                if assignee:
                    tg = ASSIGNEE_TELEGRAM_MAP.get(assignee, '')
                    tg_str = f" (@{tg})" if tg else ""
                    hints += f"  {dept_info['name']}: {assignee}{tg_str}\n"
            
            await update.message.reply_text(
                "❌ Формат: /assign TASK-KEY логин\n"
                "Пример: /assign HR-5 phozik\n\n"
                f"{hints}"
            )
            return
        
        issue_key = context.args[0].upper()
        new_assignee = context.args[1].lower()
        
        # Проверяем задачу в БД
        task_info = self.db.get_task(issue_key)
        if not task_info:
            await update.message.reply_text(f"❌ Задача {issue_key} не найдена в базе.")
            return
        
        result = self.tracker_client.update_issue_assignee(issue_key, new_assignee)
        
        if result:
            # Обновляем в БД
            self.db.data['tasks'][issue_key]['last_assignee'] = new_assignee
            self.db._save_db()
            
            summary = task_info.get('summary', 'Без названия')
            task_url = f"https://tracker.yandex.ru/{issue_key}"
            await update.message.reply_text(
                f"✅ Исполнитель изменён!\n\n"
                f"📌 {issue_key}\n"
                f"📝 {summary}\n"
                f"👤 Новый исполнитель: {new_assignee}\n"
                f"🔗 {task_url}"
            )
        else:
            err = self.tracker_client.last_error or 'Неизвестная ошибка'
            await update.message.reply_text(
                f"❌ Не удалось сменить исполнителя {issue_key}.\n"
                f"⚠️ Причина: {err}"
            )
    
    async def move_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /move TASK-KEY dept — пересылка задачи в другой отдел.
        Пример: /move HR-5 razrab
        """
        user_id = update.effective_user.id
        
        if user_id not in TASK_CLOSER_IDS and not self.is_manager(user_id):
            await update.message.reply_text("❌ У вас нет прав на перемещение задач.")
            return
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Формат: /move TASK-KEY отдел\n"
                "Пример: /move HR-5 razrab\n\n"
                "Доступные отделы: " + ", ".join(DEPARTMENT_MAPPING.keys())
            )
            return
        
        issue_key = context.args[0].upper()
        target_dept = context.args[1].lower()
        
        if target_dept not in DEPARTMENT_MAPPING:
            await update.message.reply_text(
                f"❌ Отдел '{target_dept}' не найден.\n"
                "Доступные: " + ", ".join(DEPARTMENT_MAPPING.keys())
            )
            return
        
        # Проверяем задачу в БД
        task_info = self.db.get_task(issue_key)
        if not task_info:
            await update.message.reply_text(f"❌ Задача {issue_key} не найдена в базе.")
            return
        
        target = DEPARTMENT_MAPPING[target_dept]
        target_queue = target['queue']
        target_name = target['name']
        target_assignee = target.get('assignee')
        
        # Создаём новую задачу в целевой очереди
        summary = task_info.get('summary', 'Без названия')
        old_dept = task_info.get('department', '')
        old_name = DEPARTMENT_MAPPING.get(old_dept, {}).get('name', old_dept)
        
        description = (
            f"📋 Перемещена из {old_name} ({issue_key})\n\n"
            f"{summary}"
        )
        
        deadline = self.get_deadline_date()
        new_issue = self.tracker_client.create_issue(
            queue=target_queue,
            summary=summary,
            description=description,
            assignee=target_assignee,
            priority=DEFAULT_PRIORITY,
            deadline=deadline,
            tags=['telegram', target_dept, 'moved']
        )
        
        if new_issue:
            new_key = new_issue.get('key')
            new_url = f"https://tracker.yandex.ru/{new_key}"
            
            # Сохраняем новую задачу в БД
            self.db.add_task(
                issue_key=new_key,
                chat_id=task_info.get('chat_id', 0),
                message_id=0,
                summary=summary,
                queue=target_queue,
                department=target_dept,
                creator_id=task_info.get('creator_id', user_id)
            )
            
            # Закрываем старую задачу
            self.tracker_client.add_comment(
                issue_key, f"➡️ Задача перемещена в {target_name}: {new_key}"
            )
            self.tracker_client.update_issue_status(issue_key, 'closed')
            self.db.update_task_status(issue_key, 'closed')
            
            await update.message.reply_text(
                f"✅ Задача перемещена!\n\n"
                f"📌 {issue_key} → {new_key}\n"
                f"🏢 {old_name} → {target_name}\n"
                f"👤 Исполнитель: {target_assignee or 'не назначен'}\n"
                f"🔗 {new_url}"
            )
            logger.info(f"➡️ Задача {issue_key} перемещена в {target_dept} → {new_key}")
        else:
            err = self.tracker_client.last_error or 'Неизвестная ошибка'
            await update.message.reply_text(
                f"❌ Не удалось переместить задачу {issue_key}.\n"
                f"⚠️ Причина: {err}"
            )
    
    async def dashboard_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработчик команды /dashboard — сводка по отделам.
        """
        all_tasks = self.db.data.get('tasks', {})
        
        dept_stats = {}
        total_open = 0
        total_closed = 0
        close_times = []
        
        for task_key, task_info in all_tasks.items():
            dept = task_info.get('department', 'other')
            dept_name = DEPARTMENT_MAPPING.get(dept, {}).get('name', dept or 'Другое')
            
            if dept_name not in dept_stats:
                dept_stats[dept_name] = {'open': 0, 'closed': 0}
            
            status = task_info.get('status', 'open')
            if status == 'open':
                dept_stats[dept_name]['open'] += 1
                total_open += 1
            else:
                dept_stats[dept_name]['closed'] += 1
                total_closed += 1
                
                # Считаем время закрытия
                created_str = task_info.get('created_at', '')
                updated_str = task_info.get('updated_at', '')
                if created_str and updated_str:
                    try:
                        created = datetime.fromisoformat(created_str)
                        updated = datetime.fromisoformat(updated_str)
                        close_times.append((updated - created).total_seconds() / 3600)
                    except Exception:
                        pass
        
        avg_hours = sum(close_times) / len(close_times) if close_times else 0
        
        if avg_hours >= 24:
            avg_text = f"{avg_hours / 24:.1f} дн."
        else:
            avg_text = f"{avg_hours:.1f} ч."
        
        text = (
            f"📊 Дашборд\n\n"
            f"📝 Открыто: {total_open}\n"
            f"✅ Закрыто: {total_closed}\n"
            f"⏱ Среднее время закрытия: {avg_text}\n\n"
            f"📋 По отделам:\n"
        )
        
        for dept_name in sorted(dept_stats.keys()):
            stats = dept_stats[dept_name]
            text += f"  {dept_name}: 📝{stats['open']} открыто / ✅{stats['closed']} закрыто\n"
        
        if not dept_stats:
            text += "  Нет данных\n"
        
        await update.message.reply_text(text)
    
    async def _post_init(self, application: Application) -> None:
        """Callback после инициализации — устанавливаем команды для всплывающего меню"""
        commands = [
            ("start", "🚀 Начало работы"),
            ("help", "❓ Справка"),
            ("mytasks", "📋 Мои задачи"),
            ("assigned", "👤 Назначенные на меня"),
            ("move", "➡️ Переместить задачу"),
        ]
        
        try:
            await application.bot.set_my_commands(commands)
            logger.info("✅ Команды установлены для всплывающего меню")
        except Exception as e:
            logger.error(f"❌ Ошибка установки команд: {e}")
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        
        # Создаем приложение с post_init для установки команд
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(self._post_init).build()
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("mytasks", self.mytasks_command))
        application.add_handler(CommandHandler("assigned", self.assigned_command))
        application.add_handler(CommandHandler("move", self.move_command))
        
        # Регистрируем обработчик кнопок
        application.add_handler(CallbackQueryHandler(self.handle_complete_task))
        
        # Регистрируем обработчик сообщений (текст + фото с подписью)
        application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND,
                self.handle_message
            )
        )
        
        # Фоновая синхронизация статусов + напоминания (каждые 5 минут)
        application.job_queue.run_repeating(
            self._periodic_sync_job,
            interval=300,  # 5 минут
            first=60       # первый запуск через 1 минуту
        )
        
        # Еженедельный отчёт — каждый понедельник в 09:00 МСК
        from datetime import time as dt_time
        application.job_queue.run_daily(
            self._weekly_report_job,
            time=dt_time(hour=6, minute=0, tzinfo=timezone.utc),  # 09:00 МСК = 06:00 UTC
            days=(0,)  # 0 = понедельник
        )
        
        # Ежедневные напоминания в 9:55 МСК (менеджерам)
        reminder_hour, reminder_minute = map(int, DAILY_REMINDER_TIME.split(':'))
        # Конвертируем МСК в UTC (МСК - 3 часа)
        utc_hour = (reminder_hour - 3) % 24
        application.job_queue.run_daily(
            self._daily_reminder_job,
            time=dt_time(hour=utc_hour, minute=reminder_minute, tzinfo=timezone.utc)
        )
        
        # Приглашение на дейли митинг в 10:55 МСК
        application.job_queue.run_daily(
            self._daily_meeting_reminder_job,
            time=dt_time(hour=7, minute=55, tzinfo=timezone.utc)  # 10:55 МСК = 07:55 UTC
        )
        
        # Напоминания исполнителям и наблюдателям в 10:00 МСК
        application.job_queue.run_daily(
            self._assignee_reminder_job,
            time=dt_time(hour=7, minute=0, tzinfo=timezone.utc)  # 10:00 МСК = 07:00 UTC
        )
        
        # Напоминания о просроченных задачах в 9:30 и 15:30 МСК
        application.job_queue.run_daily(
            self._overdue_reminder_job,
            time=dt_time(hour=6, minute=30, tzinfo=timezone.utc)  # 09:30 МСК = 06:30 UTC
        )
        application.job_queue.run_daily(
            self._overdue_reminder_job,
            time=dt_time(hour=12, minute=30, tzinfo=timezone.utc)  # 15:30 МСК = 12:30 UTC
        )
        
        # Запускаем бота
        logger.info("Бот запущен и готов к работе!")
        logger.info(f"Настроено отделов: {len(DEPARTMENT_MAPPING)}")
        logger.info(f"Менеджеров в системе: {len(MANAGER_IDS)}")
        logger.info("🔄 Синхронизация + напоминания: каждые 5 минут")
        logger.info("📊 Еженедельный отчёт: понедельник 09:00")
        logger.info("Партнеры указывают свой ID в формате WEB#123")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = TrackerBot()
    bot.run()
