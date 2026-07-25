-- 002: ядро оценки переехало с четырёх осей MBTI на пять черт Big Five (Этап 3B).
--
-- signals.axis хранил "EI"/"SN"/"TF"/"JP", теперь signals.trait хранит
-- "openness"/"conscientiousness"/"extraversion"/"agreeableness"/"neuroticism",
-- а direction — "high"/"low" вместо полюсов MBTI.
--
-- synthesis.axes_confidence переименована симметрично контракту SynthesisResult.
--
-- Применить:  psql "$DATABASE_URL" -f migrations/002_signals_axis_to_trait.sql
-- Откатить:   ALTER TABLE signals RENAME COLUMN trait TO axis;
--             ALTER TABLE synthesis RENAME COLUMN traits_confidence TO axes_confidence;
--
-- Данные НЕ конвертируются: на момент миграции все таблицы пусты (проверено),
-- а честного отображения "EI" -> черта всё равно не существует — Neuroticism
-- в старой схеме не выражался вовсе. Строки со старыми значениями, если они
-- где-то появятся, надо удалять, а не переводить.

ALTER TABLE signals RENAME COLUMN axis TO trait;
ALTER TABLE signals RENAME CONSTRAINT uq_signal_nodup TO uq_signal_nodup_trait;

ALTER TABLE synthesis RENAME COLUMN axes_confidence TO traits_confidence;
