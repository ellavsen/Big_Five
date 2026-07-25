-- 001: снимок ConversationState для восстановления диалога после рестарта процесса.
--
-- Зачем отдельный файл, а не create_all: init_db() разворачивает схему с нуля,
-- но в УЖЕ существующую таблицу новую колонку не добавит. Alembic пока не заводим
-- (см. docs/ROADMAP.md), поэтому миграции — нумерованные .sql, применяются вручную.
--
-- Применить:  psql "$DATABASE_URL" -f migrations/001_add_sessions_state_json.sql
-- Откатить:   ALTER TABLE sessions DROP COLUMN state_json;
--
-- Безопасно: колонка nullable и без DEFAULT — PostgreSQL правит только каталог,
-- таблица не перезаписывается. IF NOT EXISTS делает команду идемпотентной.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS state_json JSONB;
