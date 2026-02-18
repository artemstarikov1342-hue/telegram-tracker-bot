#!/bin/bash

echo "═══════════════════════════════════════════════════════════════"
echo "  АВТОМАТИЧЕСКАЯ НАСТРОЙКА БОТА НА СЕРВЕРЕ"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Обновление системы
echo "[1/6] Обновление системы..."
apt update && apt upgrade -y

# Установка Python и зависимостей
echo ""
echo "[2/6] Установка Python..."
apt install python3 python3-pip unzip -y

# Установка Python библиотек
echo ""
echo "[3/6] Установка зависимостей бота..."
pip3 install python-telegram-bot python-dotenv requests

# Настройка systemd службы
echo ""
echo "[4/6] Настройка автозапуска..."
cat > /etc/systemd/system/telegram-bot.service << 'EOF'
[Unit]
Description=Telegram Tracker Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram_bot
ExecStart=/usr/bin/python3 /root/telegram_bot/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Активация службы
echo ""
echo "[5/6] Активация службы..."
systemctl daemon-reload
systemctl enable telegram-bot

# Запуск бота
echo ""
echo "[6/6] Запуск бота..."
systemctl start telegram-bot

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ГОТОВО!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "✅ Бот установлен и запущен!"
echo ""
echo "Проверка статуса:"
echo "  systemctl status telegram-bot"
echo ""
echo "Просмотр логов:"
echo "  journalctl -u telegram-bot -f"
echo ""
echo "═══════════════════════════════════════════════════════════════"
