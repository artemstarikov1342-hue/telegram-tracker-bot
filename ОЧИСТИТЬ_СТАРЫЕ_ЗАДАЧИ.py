"""Очистка старых задач из БД"""
import json

# Читаем БД
with open('tasks_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("\n" + "="*60)
print("  ОЧИСТКА СТАРЫХ ЗАДАЧ")
print("="*60 + "\n")

# Список задач для удаления (старые из MNG в личке)
tasks_to_remove = []

for task_key, task_info in list(data['tasks'].items()):
    chat_id = task_info.get('chat_id')
    queue = task_info.get('queue', '')
    status = task_info.get('status', '')
    
    # Удаляем старые задачи из MNG в личке (chat_id = 8337630955)
    if chat_id == 8337630955 and queue == 'MNG':
        tasks_to_remove.append(task_key)
        print(f"❌ Удаляю: {task_key} (личка, MNG, {status})")

# Удаляем задачи
for task_key in tasks_to_remove:
    del data['tasks'][task_key]

# Обновляем chats
for chat_id, task_list in data['chats'].items():
    data['chats'][chat_id] = [t for t in task_list if t not in tasks_to_remove]

# Сохраняем
with open('tasks_db.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✅ Удалено задач: {len(tasks_to_remove)}")
print("✅ БД обновлена!")
print("\n" + "="*60 + "\n")
