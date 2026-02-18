Set WshShell = CreateObject("WScript.Shell")

' Установка
MsgBox "Сейчас начнётся установка зависимостей." & vbCrLf & vbCrLf & "Это займёт 1-2 минуты. Не закрывайте окно!", vbInformation, "Установка Telegram Tracker Bot"

WshShell.Run "cmd /k python install_now.py", 1, True

' Запуск
result = MsgBox("Установка завершена!" & vbCrLf & vbCrLf & "Запустить бота сейчас?", vbYesNo + vbQuestion, "Запуск бота")

If result = vbYes Then
    WshShell.Run "cmd /k python bot.py", 1, False
    MsgBox "Бот запущен!" & vbCrLf & vbCrLf & "Откройте Telegram и отправьте боту: /start" & vbCrLf & vbCrLf & "Для остановки закройте окно cmd", vbInformation, "Бот работает"
End If

Set WshShell = Nothing
