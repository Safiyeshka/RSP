FROM python:3.9-alpine

WORKDIR /app

# Установка системных зависимостей
RUN apk add --no-cache \
  postgresql-dev \
  gcc \
  python3-dev \
  musl-dev \
  linux-headers

# Копирование requirements и установка Python пакетов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание директории для логов
RUN mkdir -p /app/logs

EXPOSE 5000

CMD ["python", "app.py"]



# Используем официальный Python образ
# FROM python:3.9-slim

# # Устанавливаем рабочую директорию
# WORKDIR /app

# # Копируем файл с зависимостями
# COPY requirements.txt .

# # Устанавливаем зависимости
# RUN pip install -r requirements.txt

# # Копируем весь проект
# COPY . .

# # Открываем порт
# EXPOSE 5000

# # Запускаем приложение
# CMD ["python", "app.py"]

