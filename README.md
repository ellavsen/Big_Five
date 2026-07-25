после того как установили все библиотеки проверь python, должно быть 3.12... (python 3.13 не совместим с последней версией телеграм бота в моем "requirements.txt"), для базы данных проверяем 
.env там хранится ключ к OPENAI_API_KEY, TELEGRAM_BOT_TOKEN и DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@localhost:5432/neuro_db"(где USER имя твоего компьютера(системы (проверить командой в терминале whoami)) и если есть пароль, а neuro_db создаём в терминале после того как установим postgresql@16) далее в терминале устанавливаем : "brew install postgresql@16", после установки запускаем сервис "brew services start postgresql@16" 
Проверка:
brew services list
Должно быть started.
