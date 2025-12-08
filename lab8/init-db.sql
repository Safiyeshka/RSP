-- init-db.sql
-- Создание базы данных (если еще не существует)
SELECT 'CREATE DATABASE seriesdb'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'seriesdb')\gexec

-- Подключение к созданной базе данных
\c seriesdb

-- Создание таблицы series
CREATE TABLE IF NOT EXISTS series (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    year INTEGER,
    episodes INTEGER,
    rating FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Вставка тестовых данных
INSERT INTO series (title, year, episodes, rating) VALUES
    ('Великолепный век', 2011, 139, 8.2),
    ('Любовь напрокат', 2020, 52, 7.8),
    ('Постучи в мою дверь', 2020, 52, 8.1),
    ('Стамбульская невеста', 2023, 45, 7.9),
    ('Вдребезги', 2022, 36, 8.4)
ON CONFLICT DO NOTHING;