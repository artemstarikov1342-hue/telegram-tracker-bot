"""
Модуль для работы с базой данных задач
Хранит связи между задачами Яндекс.Трекера и чатами Telegram
"""
import json
import logging
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskDatabase:
    """Класс для управления базой данных задач"""
    
    def __init__(self, db_file: str = 'tasks_db.json'):
        """
        Инициализация базы данных
        
        Args:
            db_file: Путь к файлу базы данных
        """
        self.db_file = Path(db_file)
        self.data = self._load_db()
    
    def _load_db(self) -> Dict:
        """Загрузка данных из файла"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Миграция: добавляем 'users' и 'usernames' если их нет
                if 'users' not in data:
                    data['users'] = {}
                if 'usernames' not in data:
                    data['usernames'] = {}
                
                # Обновляем маппинг username -> user_id на основе существующих данных
                for user_id, user_info in data['users'].items():
                    username = user_info.get('username')
                    if username:
                        data['usernames'][username] = int(user_id)
                
                return data
            except Exception as e:
                logger.error(f"Ошибка загрузки БД: {e}")
                data = {'tasks': {}, 'users': {}, 'usernames': {}}
                return data
        else:
            # Создаем новую БД
            data = {'tasks': {}, 'users': {}, 'usernames': {}}
            self._save_db_direct(data)
            return data
    
    def _save_db(self) -> bool:
        """Сохранение данных в файл"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
            return False
    
    def _save_db_direct(self, data: Dict) -> bool:
        """Прямое сохранение данных в файл (для _load_db)"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
            return False
    
    def add_task(
        self,
        issue_key: str,
        chat_id: int,
        message_id: int,
        summary: str,
        queue: str,
        department: Optional[str] = None,
        creator_id: Optional[int] = None
    ) -> bool:
        """
        Добавление задачи в БД
        
        Args:
            issue_key: Ключ задачи в Трекере (например, DEV-123)
            chat_id: ID чата Telegram
            message_id: ID сообщения в Telegram
            summary: Название задачи
            queue: Очередь
            department: Отдел
            creator_id: Telegram ID создателя задачи
            
        Returns:
            True если успешно, False иначе
        """
        self.data['tasks'][issue_key] = {
            'chat_id': chat_id,
            'message_id': message_id,
            'summary': summary,
            'queue': queue,
            'department': department,
            'creator_id': creator_id,
            'created_at': datetime.now().isoformat(),
            'status': 'open'
        }
        
        # Добавляем задачу в список задач чата
        chat_key = str(chat_id)
        if chat_key not in self.data['chats']:
            self.data['chats'][chat_key] = []
        
        self.data['chats'][chat_key].append(issue_key)
        
        # Добавляем задачу в список задач пользователя
        if creator_id:
            user_key = str(creator_id)
            if user_key not in self.data['users']:
                self.data['users'][user_key] = []
            self.data['users'][user_key].append(issue_key)
        
        return self._save_db()
    
    def get_task(self, issue_key: str) -> Optional[Dict]:
        """
        Получение информации о задаче
        
        Args:
            issue_key: Ключ задачи
            
        Returns:
            Словарь с данными задачи или None
        """
        return self.data['tasks'].get(issue_key)
    
    def update_task_status(self, issue_key: str, status: str) -> bool:
        """
        Обновление статуса задачи
        
        Args:
            issue_key: Ключ задачи
            status: Новый статус
            
        Returns:
            True если успешно, False иначе
        """
        if issue_key in self.data['tasks']:
            self.data['tasks'][issue_key]['status'] = status
            self.data['tasks'][issue_key]['updated_at'] = datetime.now().isoformat()
            return self._save_db()
        return False
    
    def get_chat_tasks(self, chat_id: int, status: Optional[str] = None) -> List[str]:
        """
        Получение всех задач чата
        
        Args:
            chat_id: ID чата
            status: Фильтр по статусу (опционально)
            
        Returns:
            Список ключей задач
        """
        chat_key = str(chat_id)
        task_keys = self.data['chats'].get(chat_key, [])
        
        if status:
            return [
                key for key in task_keys
                if self.data['tasks'].get(key, {}).get('status') == status
            ]
        
        return task_keys
    
    def get_user_tasks(self, user_id: int, status: Optional[str] = None) -> List[str]:
        """
        Получение всех задач пользователя (по creator_id)
        
        Args:
            user_id: Telegram ID пользователя
            status: Фильтр по статусу (опционально)
            
        Returns:
            Список ключей задач
        """
        user_key = str(user_id)
        task_keys = self.data['users'].get(user_key, [])
        
        if status:
            return [
                key for key in task_keys
                if self.data['tasks'].get(key, {}).get('status') == status
            ]
        
        return task_keys
    
    def search_task_by_text(self, chat_id: int, search_text: str) -> Optional[str]:
        """
        Поиск задачи по тексту в чате
        
        Args:
            chat_id: ID чата
            search_text: Текст для поиска
            
        Returns:
            Ключ задачи или None
        """
        search_text = search_text.lower()
        chat_tasks = self.get_chat_tasks(chat_id)
        
        for task_key in chat_tasks:
            task = self.get_task(task_key)
            if task and search_text in task.get('summary', '').lower():
                return task_key
        
        return None
    
    def register_user(self, user_id: int, username: str, first_name: str = "") -> None:
        """
        Регистрация пользователя в БД для маппинга username -> user_id
        
        Args:
            user_id: Telegram ID пользователя
            username: Telegram username (без @)
            first_name: Имя пользователя
        """
        user_key = str(user_id)
        
        # Сохраняем информацию о пользователе
        if user_key not in self.data['users']:
            self.data['users'][user_key] = {}
        
        self.data['users'][user_key].update({
            'username': username.lower(),
            'first_name': first_name,
            'registered_at': datetime.now().isoformat()
        })
        
        # Обновляем маппинг username -> user_id
        if username:
            self.data['usernames'][username.lower()] = user_id
        
        self._save_db()
        logger.info(f"✅ Пользователь зарегистрирован: {username} -> {user_id}")
    
    def get_telegram_id_by_username(self, username: str) -> Optional[int]:
        """
        Получение Telegram ID по username
        
        Args:
            username: Telegram username (без @)
            
        Returns:
            Telegram ID или None
        """
        return self.data['usernames'].get(username.lower())
    
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """
        Получение информации о пользователе
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Информация о пользователе или None
        """
        return self.data['users'].get(str(user_id))
