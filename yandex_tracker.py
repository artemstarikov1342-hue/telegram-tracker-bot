"""
Модуль для работы с Яндекс.Трекером
"""
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class YandexTrackerClient:
    """Клиент для работы с API Яндекс.Трекера"""
    
    BASE_URL = 'https://api.tracker.yandex.net/v2'
    
    def __init__(self, token: str, org_id: str):
        """
        Инициализация клиента
        
        Args:
            token: OAuth токен для доступа к API
            org_id: ID организации в Яндекс.Трекере
        """
        self.token = token
        self.org_id = org_id
        self.last_error = ''
        self.headers = {
            'Authorization': f'OAuth {token}',
            'X-Org-ID': org_id,
            'Content-Type': 'application/json'
        }
    
    def create_issue(
        self,
        queue: str,
        summary: str,
        description: str,
        assignee: Optional[str] = None,
        priority: str = 'normal',
        tags: Optional[list] = None,
        deadline: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создание задачи в Яндекс.Трекере
        
        Args:
            queue: Ключ очереди
            summary: Название задачи
            description: Описание задачи
            assignee: Логин исполнителя
            priority: Приоритет (trivial, minor, normal, critical, blocker)
            tags: Список тегов
            deadline: Дедлайн в формате YYYY-MM-DD
            
        Returns:
            Словарь с данными созданной задачи или None в случае ошибки
        """
        url = f'{self.BASE_URL}/issues'
        
        payload = {
            'queue': queue,
            'summary': summary,
            'description': description,
            'priority': priority
        }
        
        if assignee:
            payload['assignee'] = assignee
        
        if tags:
            payload['tags'] = tags
        
        if deadline:
            payload['deadline'] = deadline
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            issue_data = response.json()
            logger.info(f"Создана задача: {issue_data.get('key')} - {summary}")
            return issue_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при создании задачи: {e}")
            self.last_error = str(e)
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Ответ сервера: {e.response.text}")
                try:
                    err_data = e.response.json()
                    msgs = err_data.get('errorMessages', [])
                    errs = err_data.get('errors', {})
                    if msgs:
                        self.last_error = '; '.join(msgs)
                    elif errs:
                        self.last_error = '; '.join(f"{k}: {v}" for k, v in errs.items())
                except Exception:
                    pass
            return None
    
    def get_queue_info(self, queue_key: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации об очереди
        
        Args:
            queue_key: Ключ очереди
            
        Returns:
            Информация об очереди или None
        """
        url = f'{self.BASE_URL}/queues/{queue_key}'
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении информации об очереди {queue_key}: {e}")
            return None
    
    def create_queue(self, queue_key: str, queue_name: str, lead: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Создание новой очереди в Яндекс.Трекере
        
        Args:
            queue_key: Ключ очереди (например, WEB2)
            queue_name: Название очереди
            lead: Логин руководителя очереди (опционально)
            
        Returns:
            Данные созданной очереди или None
        """
        url = f'{self.BASE_URL}/queues'
        
        # Получаем информацию о текущем пользователе для lead
        if not lead:
            try:
                me_url = f'{self.BASE_URL}/myself'
                response = requests.get(me_url, headers=self.headers, timeout=10)
                response.raise_for_status()
                user_info = response.json()
                lead = user_info.get('login')
                logger.info(f"ℹ️ Использую текущего пользователя как lead: {lead}")
            except Exception as e:
                logger.error(f"⚠️ Не удалось получить текущего пользователя: {e}")
                return None
        
        # Получаем список доступных workflow
        try:
            workflows_url = f'{self.BASE_URL}/workflows'
            wf_response = requests.get(workflows_url, headers=self.headers, timeout=10)
            wf_response.raise_for_status()
            workflows = wf_response.json()
            
            # Берем первый доступный workflow
            default_workflow = None
            if workflows and len(workflows) > 0:
                default_workflow = workflows[0].get('id')
                logger.info(f"ℹ️ Использую workflow: {default_workflow}")
        except Exception as e:
            logger.error(f"⚠️ Не удалось получить список workflows: {e}")
            return None
        
        if not default_workflow:
            logger.error("❌ Не найден ни один доступный workflow")
            return None
        
        # Проверяем длину ключа (должен быть 2-15 символов, только латиница и цифры)
        if len(queue_key) < 2 or len(queue_key) > 15:
            logger.error(f"❌ Неверная длина ключа очереди: {len(queue_key)} символов (должно быть 2-15)")
            return None
        
        if not queue_key.replace('_', '').replace('-', '').isalnum():
            logger.error(f"❌ Ключ очереди содержит недопустимые символы: {queue_key}")
            return None
        
        payload = {
            'key': queue_key.upper(),  # Ключ в верхнем регистре
            'name': queue_name,
            'lead': lead,  # ОБЯЗАТЕЛЬНЫЙ параметр!
            'defaultType': 'task',
            'defaultPriority': 'critical',
            'issueTypesConfig': [  # ОБЯЗАТЕЛЬНЫЙ параметр!
                {
                    'issueType': 'task',
                    'workflow': default_workflow,  # Используем доступный workflow
                    'resolutions': ['fixed', 'wontFix', 'duplicate']
                }
            ]
        }
        
        logger.info(f"📋 Payload для создания очереди: key={payload['key']}, name={payload['name']}")
        
        try:
            logger.info(f"🆕 Создаю новую очередь: {queue_key} ({queue_name})")
            logger.info(f"   Lead: {lead}")
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"✅ Очередь {queue_key} успешно создана!")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка при создании очереди {queue_key}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"   Код ответа: {e.response.status_code}")
                logger.error(f"   Ответ сервера: {e.response.text}")
            return None
    
    def get_user_info(self, user_login: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о пользователе
        
        Args:
            user_login: Логин пользователя
            
        Returns:
            Информация о пользователе или None
        """
        url = f'{self.BASE_URL}/users/{user_login}'
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении информации о пользователе {user_login}: {e}")
            return None
    
    def add_comment(self, issue_key: str, comment_text: str) -> Optional[Dict[str, Any]]:
        """
        Добавление комментария к задаче
        
        Args:
            issue_key: Ключ задачи (например, QUEUE-123)
            comment_text: Текст комментария
            
        Returns:
            Данные комментария или None
        """
        url = f'{self.BASE_URL}/issues/{issue_key}/comments'
        
        payload = {
            'text': comment_text
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при добавлении комментария к {issue_key}: {e}")
            return None
    
    def update_issue_status(self, issue_key: str, status: str) -> Optional[Dict[str, Any]]:
        """
        Изменение статуса задачи
        
        Args:
            issue_key: Ключ задачи (например, QUEUE-123)
            status: Новый статус (например, 'closed', 'resolved')
            
        Returns:
            Обновленные данные задачи или None
        """
        try:
            logger.info(f"🔄 Получаю доступные переходы для задачи {issue_key}...")
            
            # Сначала получаем доступные переходы
            transitions_url = f'{self.BASE_URL}/issues/{issue_key}/transitions'
            response = requests.get(
                transitions_url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            transitions = response.json()
            
            logger.info(f"📋 Найдено переходов: {len(transitions)}")
            for trans in transitions:
                to_status = trans.get('to', {})
                logger.info(f"  → ID: {trans.get('id')}, к статусу: {to_status.get('display')} (key: {to_status.get('key')})")
            
            # Ищем переход на нужный статус
            target_transition = None
            target_statuses = ['closed', 'resolved', 'done', 'завершена', 'закрыта']
            
            logger.info(f"🔍 Ищу переход к одному из статусов: {target_statuses}")
            
            for transition in transitions:
                to_status = transition.get('to', {})
                status_key = to_status.get('key', '').lower()
                status_display = to_status.get('display', '').lower()
                
                logger.info(f"  🔎 Проверяю: key={status_key}, display={status_display}")
                
                if status_key in target_statuses or status_display in target_statuses:
                    target_transition = transition
                    logger.info(f"  ✅ НАЙДЕН! Переход ID: {transition.get('id')} → {to_status.get('display')}")
                    break
            
            # Если прямого перехода нет, пробуем через промежуточный статус
            if not target_transition:
                logger.warning(f"⚠️ Прямого перехода к 'closed' нет")
                logger.info(f"🔄 Пробую перевести через промежуточный статус 'В работе'...")
                
                # Ищем переход в "В работе"
                progress_transition = None
                progress_statuses = ['inprogress', 'в работе']
                
                for transition in transitions:
                    to_status = transition.get('to', {})
                    status_key = to_status.get('key', '').lower()
                    status_display = to_status.get('display', '').lower()
                    
                    if status_key in progress_statuses or status_display in progress_statuses:
                        progress_transition = transition
                        logger.info(f"  ✅ НАЙДЕН переход в 'В работе': ID {transition.get('id')}")
                        break
                
                if progress_transition:
                    # Переводим в "В работе"
                    transition_id = progress_transition.get('id')
                    execute_url = f'{self.BASE_URL}/issues/{issue_key}/transitions/{transition_id}/_execute'
                    
                    logger.info(f"🚀 ШАГ 1: Перевожу в 'В работе'...")
                    response = requests.post(execute_url, json={}, headers=self.headers, timeout=10)
                    response.raise_for_status()
                    logger.info(f"✅ Задача переведена в 'В работе'")
                    
                    # Получаем новые доступные переходы
                    response = requests.get(transitions_url, headers=self.headers, timeout=10)
                    response.raise_for_status()
                    transitions = response.json()
                    
                    logger.info(f"📋 Новые переходы после 'В работе': {len(transitions)}")
                    for trans in transitions:
                        to_status = trans.get('to', {})
                        logger.info(f"  → ID: {trans.get('id')}, к статусу: {to_status.get('display')} (key: {to_status.get('key')})")
                    
                    # Ищем переход к "Закрыт"
                    for transition in transitions:
                        to_status = transition.get('to', {})
                        status_key = to_status.get('key', '').lower()
                        status_display = to_status.get('display', '').lower()
                        
                        if status_key in target_statuses or status_display in target_statuses:
                            target_transition = transition
                            logger.info(f"  ✅ НАЙДЕН переход к 'Закрыт': ID {transition.get('id')}")
                            break
            
            if not target_transition:
                logger.error(f"❌ Не найден переход для закрытия задачи {issue_key}")
                logger.error(f"   Доступные переходы: {[t.get('to', {}).get('key') for t in transitions]}")
                return None
            
            # Выполняем переход
            transition_id = target_transition.get('id')
            execute_url = f'{self.BASE_URL}/issues/{issue_key}/transitions/{transition_id}/_execute'
            
            # Для закрытия задачи нужно указать резолюцию
            payload = {
                'resolution': 'fixed'  # Решена
            }
            
            logger.info(f"🚀 ШАГ ФИНАЛ: Выполняю переход {transition_id} для задачи {issue_key}...")
            logger.info(f"   URL: {execute_url}")
            logger.info(f"   Payload: {payload}")
            
            response = requests.post(
                execute_url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"✅ Статус задачи {issue_key} изменен на {target_transition.get('to', {}).get('display')}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка при изменении статуса {issue_key}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"   Код ответа: {e.response.status_code}")
                logger.error(f"   Ответ сервера: {e.response.text}")
            return None
    
    def get_issue(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о задаче
        
        Args:
            issue_key: Ключ задачи (например, QUEUE-123)
            
        Returns:
            Информация о задаче или None
        """
        url = f'{self.BASE_URL}/issues/{issue_key}'
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении задачи {issue_key}: {e}")
            return None
    
    def create_board(self, board_name: str, queue: str, filter_tag: str) -> Optional[Dict[str, Any]]:
        """
        Создание доски в Яндекс.Трекере с фильтром по тегу
        
        Args:
            board_name: Название доски (например: 'WEB2')
            queue: Ключ очереди
            filter_tag: Тег для фильтрации (например: 'WEB2')
            
        Returns:
            Данные созданной доски или None
        """
        url = f'{self.BASE_URL}/boards'
        
        payload = {
            'name': board_name,
            'boardType': 'default',
            'filter': {
                'queue': queue,
                'tags': [filter_tag]
            }
        }
        
        try:
            logger.info(f"🆕 Создаю новую доску: {board_name}")
            logger.info(f"   Очередь: {queue}, Фильтр по тегу: {filter_tag}")
            
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            board_data = response.json()
            logger.info(f"✅ Доска {board_name} успешно создана! ID: {board_data.get('id')}")
            return board_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка при создании доски {board_name}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"   Код ответа: {e.response.status_code}")
                logger.error(f"   Ответ сервера: {e.response.text}")
            return None
