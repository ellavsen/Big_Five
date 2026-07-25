-- 003: починка типов колонок, забытая в миграции 002.
--
-- 002 переименовала signals.axis -> signals.trait, но НЕ изменила тип. Колонка
-- осталась varchar(8) от коротких имён осей MBTI ("EI", "SN"), а имена черт
-- длиннее: "conscientiousness" — 17 символов. То же с direction: varchar(4)
-- от полюсов "E"/"I", а теперь там "high"/"low".
--
-- Что это ломало: КАЖДАЯ вставка наблюдения падала на
-- StringDataRightTruncationError, а repo.add_signals глушил исключение целиком
-- («на дублях просто откатываем») — то есть сигналы молча не сохранялись вообще.
-- Найдено сквозным прогоном: 21 сообщение в БД и 0 наблюдений при 16 в памяти.
--
-- Применить:  psql "$DATABASE_URL" -f migrations/003_fix_signal_column_types.sql
-- Откатить:   смысла нет — старые типы просто не вмещают текущие значения.
--
-- Безопасно: расширение varchar не переписывает таблицу и не теряет данные.

ALTER TABLE signals ALTER COLUMN trait TYPE VARCHAR(24);
ALTER TABLE signals ALTER COLUMN direction TYPE VARCHAR(8);
