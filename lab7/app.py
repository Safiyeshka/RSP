from flask import Flask, request, jsonify, g
import logging
import time
import sqlite3
import datetime
from flask_cors import CORS
import redis
import json
import os

app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

# Детальная настройка логирования как в предыдущей работе
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('series_app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TurkishSeriesAPI')

# Глобальная переменная для Redis (вместо использования g вне контекста)
_redis_client = None

# Инициализация Redis
def get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        _redis_client = redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        # Проверяем подключение
        _redis_client.ping()
        logger.info("✅ Redis подключен успешно")
        return _redis_client
    except (redis.ConnectionError, redis.TimeoutError) as e:
        logger.warning(f"⚠️ Redis недоступен: {str(e)}, работаем без кэширования")
        _redis_client = None
        return None

# Настройка базы данных
def init_db():
    conn = sqlite3.connect('series.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            year INTEGER,
            episodes INTEGER,
            rating REAL
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM series")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('''
            INSERT INTO series (title, year, episodes, rating) VALUES (?, ?, ?, ?)
        ''', [
            ('Великолепный век', 2011, 139, 8.2),
            ('Любовь напрокат', 2020, 52, 7.8),
            ('Постучи в мою дверь', 2020, 52, 8.1)
        ])
        logger.info("✅ Добавлены начальные данные в базу")
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('series.db')
    conn.row_factory = sqlite3.Row
    return conn

# Инициализируем базу при старте
init_db()

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

# Словарь для хранения статистики
request_stats = {
    'total_requests': 0,
    'average_time': 0,
    'endpoints': {}
}

def update_statistics(endpoint, execution_time):
    request_stats['total_requests'] += 1
    
    total_time = request_stats['average_time'] * (request_stats['total_requests'] - 1) + execution_time
    request_stats['average_time'] = total_time / request_stats['total_requests']
    
    if endpoint not in request_stats['endpoints']:
        request_stats['endpoints'][endpoint] = {
            'count': 0,
            'total_time': 0,
            'average_time': 0,
            'min_time': float('inf'),
            'max_time': 0
        }
    
    endpoint_stats = request_stats['endpoints'][endpoint]
    endpoint_stats['count'] += 1
    endpoint_stats['total_time'] += execution_time
    endpoint_stats['average_time'] = endpoint_stats['total_time'] / endpoint_stats['count']
    endpoint_stats['min_time'] = min(endpoint_stats['min_time'], execution_time)
    endpoint_stats['max_time'] = max(endpoint_stats['max_time'], execution_time)

# Детальное логирование запросов как в предыдущей работе
@app.before_request
def log_request():
    logger.info(f"=== ВХОДЯЩИЙ ЗАПРОС ===")
    logger.info(f"Метод: {request.method}")
    logger.info(f"Путь: {request.path}")
    logger.info(f"IP: {request.remote_addr}")
    logger.info(f"Content-Type: {request.content_type}")
    logger.info(f"Время: {datetime.datetime.now()}")

@app.after_request
def log_response(response):
    logger.info(f"=== ИСХОДЯЩИЙ ОТВЕТ ===")
    logger.info(f"Статус: {response.status_code}")
    logger.info(f"======================")
    
    response.headers.add('Content-Type', 'application/json; charset=utf-8')
    return response

# Функции для работы с кэшем
def get_cached_data(key):
    """Получить данные из кэша Redis"""
    redis_client = get_redis()
    if not redis_client:
        return None
    
    try:
        cached = redis_client.get(key)
        if cached:
            logger.info(f"📦 Данные получены из кэша Redis: {key}")
            return json.loads(cached)
        return None
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при чтении из кэша {key}: {str(e)}")
        return None

def set_cached_data(key, data, expire_time=300):
    """Сохранить данные в кэш Redis"""
    redis_client = get_redis()
    if not redis_client:
        return
    
    try:
        redis_client.setex(key, expire_time, json.dumps(data, ensure_ascii=False))
        logger.info(f"💾 Данные сохранены в кэш Redis: {key} (TTL: {expire_time}сек)")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при записи в кэш {key}: {str(e)}")

def invalidate_cache(pattern):
    """Удалить данные из кэша по шаблону"""
    redis_client = get_redis()
    if not redis_client:
        return
    
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"🗑️ Удалены ключи кэша: {pattern}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при очистке кэша {pattern}: {str(e)}")

# 1. ПОЛУЧИТЬ ВСЕ СЕРИАЛЫ
@app.route('/series', methods=['GET'])
def get_all_series():
    start_time = time.time()
    logger.info("🔄 Обработка запроса всех сериалов")
    
    # Пробуем получить из кэша
    cache_key = "all_series"
    cached_data = get_cached_data(cache_key)
    if cached_data:
        response = jsonify(cached_data)
        execution_time = time.time() - start_time
        update_statistics("GET /series (cached)", execution_time)
        return response
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM series")
        series_list = [dict(row) for row in cursor.fetchall()]
        db.close()
        
        logger.debug(f"В базе найдено {len(series_list)} сериалов")
        for s in series_list:
            logger.debug(f" - {s['title']} (ID: {s['id']})")
        
        response_data = {
            "status": "success",
            "count": len(series_list),
            "series": series_list,
            "source": "database"
        }
        
        # Сохраняем в кэш
        set_cached_data(cache_key, response_data)
        
        response = jsonify(response_data)
        execution_time = time.time() - start_time
        update_statistics("GET /series", execution_time)
        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении сериалов: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 2. ПОЛУЧИТЬ ОДИН СЕРИАЛ
@app.route('/series/<int:series_id>', methods=['GET'])
def get_one_series(series_id):
    start_time = time.time()
    logger.info(f"🔍 Запрос на получение сериала ID: {series_id}")
    
    # Пробуем получить из кэша
    cache_key = f"series_{series_id}"
    cached_data = get_cached_data(cache_key)
    if cached_data:
        response = jsonify(cached_data)
        execution_time = time.time() - start_time
        update_statistics(f"GET /series/{series_id} (cached)", execution_time)
        return response
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
        series = cursor.fetchone()
        db.close()
        
        if series:
            series_dict = dict(series)
            logger.info(f"✅ Найден сериал: '{series_dict['title']}'")
            
            response_data = {
                "status": "success",
                "series": series_dict,
                "source": "database"
            }
            
            # Сохраняем в кэш
            set_cached_data(cache_key, response_data)
            
            response = jsonify(response_data)
            execution_time = time.time() - start_time
            update_statistics(f"GET /series/{series_id}", execution_time)
            return response
        else:
            logger.warning(f"⚠️ Сериал с ID {series_id} не найден")
            execution_time = time.time() - start_time
            update_statistics(f"GET /series/{series_id}", execution_time)
            return jsonify({"error": "Сериал не найден"}), 404
            
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics(f"GET /series/{series_id}", execution_time)
        logger.error(f"❌ Ошибка при получении сериала {series_id}: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 3. ДОБАВИТЬ СЕРИАЛ
@app.route('/series', methods=['POST'])
def add_series():
    start_time = time.time()
    logger.info("🆕 Обработка добавления нового сериала")
    
    try:
        # Проверяем Content-Type как в предыдущей работе
        if not request.is_json:
            logger.warning("❌ Неверный Content-Type. Ожидается application/json")
            return jsonify({"error": "Content-Type должен быть application/json"}), 415
            
        data = request.get_json()
        logger.info(f"Получены данные: {data}")
        
        if not data:
            logger.warning("❌ Пустой запрос")
            return jsonify({"error": "Нужны данные в формате JSON"}), 400
            
        if 'title' not in data:
            logger.warning("❌ Отсутствует название сериала")
            return jsonify({"error": "Нужно название сериала"}), 400
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO series (title, year, episodes, rating) VALUES (?, ?, ?, ?)",
            (data['title'], data.get('year', 0), data.get('episodes', 0), data.get('rating', 0.0))
        )
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        
        new_series = {
            'id': new_id,
            'title': data['title'],
            'year': data.get('year', 0),
            'episodes': data.get('episodes', 0),
            'rating': data.get('rating', 0.0)
        }
        
        logger.info(f"✅ Добавлен новый сериал: '{new_series['title']}' (ID: {new_id})")
        
        # Получаем общее количество для лога
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM series")
        total_count = cursor.fetchone()[0]
        db.close()
        logger.info(f"📊 Теперь в базе: {total_count} сериалов")
        
        # Инвалидируем кэш
        invalidate_cache("all_series")
        invalidate_cache("series_*")
        logger.info("🔄 Кэш очищен после добавления нового сериала")
        
        response = jsonify({
            "status": "success",
            "message": "Сериал добавлен",
            "series": new_series
        })
        
        execution_time = time.time() - start_time
        update_statistics("POST /series", execution_time)
        return response, 201
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics("POST /series", execution_time)
        logger.error(f"❌ Ошибка при добавлении сериала: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 4. ИЗМЕНИТЬ СЕРИАЛ
@app.route('/series/<int:series_id>', methods=['PUT'])
def update_series(series_id):
    start_time = time.time()
    logger.info(f"✏️ Запрос на обновление сериала ID: {series_id}")
    
    try:
        # Проверяем Content-Type как в предыдущей работе
        if not request.is_json:
            logger.warning("❌ Неверный Content-Type. Ожидается application/json")
            return jsonify({
                "error": "Content-Type должен быть application/json",
                "hint": "Добавьте заголовок: Content-Type: application/json"
            }), 415
            
        data = request.get_json()
        logger.info(f"Получены данные для обновления: {data}")
        
        db = get_db()
        cursor = db.cursor()
        
        # Сначала получаем текущие данные
        cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
        old_series = cursor.fetchone()
        
        if not old_series:
            db.close()
            logger.warning(f"⚠️ Сериал с ID {series_id} не найден")
            execution_time = time.time() - start_time
            update_statistics(f"PUT /series/{series_id}", execution_time)
            return jsonify({"error": "Сериал не найден"}), 404
        
        old_data = dict(old_series)
        
        # Обновляем только переданные поля
        update_fields = []
        update_values = []
        
        if 'title' in data:
            update_fields.append("title = ?")
            update_values.append(data['title'])
        if 'year' in data:
            update_fields.append("year = ?")
            update_values.append(data['year'])
        if 'episodes' in data:
            update_fields.append("episodes = ?")
            update_values.append(data['episodes'])
        if 'rating' in data:
            update_fields.append("rating = ?")
            update_values.append(data['rating'])
        
        if update_fields:
            update_values.append(series_id)
            cursor.execute(
                f"UPDATE series SET {', '.join(update_fields)} WHERE id = ?",
                update_values
            )
            db.commit()
        
        # Получаем обновленные данные
        cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
        updated_series = cursor.fetchone()
        db.close()
        
        logger.info(f"✅ Сериал обновлен: ID {series_id}")
        logger.info(f"📝 Изменения: {old_data} -> {dict(updated_series)}")
        
        # Инвалидируем кэш
        invalidate_cache("all_series")
        invalidate_cache(f"series_{series_id}")
        logger.info(f"🔄 Кэш очищен после обновления сериала {series_id}")
        
        response = jsonify({
            "status": "success",
            "message": "Сериал обновлен",
            "series": dict(updated_series)
        })
        
        execution_time = time.time() - start_time
        update_statistics(f"PUT /series/{series_id}", execution_time)
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics(f"PUT /series/{series_id}", execution_time)
        logger.error(f"❌ Ошибка при обновлении сериала {series_id}: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 5. УДАЛИТЬ СЕРИАЛ
@app.route('/series/<int:series_id>', methods=['DELETE'])
def delete_series(series_id):
    start_time = time.time()
    logger.info(f"🗑️ Запрос на удаление сериала ID: {series_id}")
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Сначала получаем сериал для логов
        cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
        series_to_delete = cursor.fetchone()
        
        if not series_to_delete:
            db.close()
            logger.warning(f"⚠️ Сериал с ID {series_id} не найден")
            execution_time = time.time() - start_time
            update_statistics(f"DELETE /series/{series_id}", execution_time)
            return jsonify({"error": "Сериал не найден"}), 404
        
        # Удаляем сериал
        cursor.execute("DELETE FROM series WHERE id = ?", (series_id,))
        db.commit()
        
        # Получаем новое количество для лога
        cursor.execute("SELECT COUNT(*) FROM series")
        remaining_count = cursor.fetchone()[0]
        db.close()
        
        deleted_data = dict(series_to_delete)
        logger.info(f"✅ Удален сериал: '{deleted_data['title']}' (ID: {series_id})")
        logger.info(f"📊 Осталось сериалов: {remaining_count}")
        
        # Инвалидируем кэш
        invalidate_cache("all_series")
        invalidate_cache(f"series_{series_id}")
        invalidate_cache("series_*")
        logger.info(f"🔄 Кэш очищен после удаления сериала {series_id}")
        
        response = jsonify({
            "status": "success",
            "message": "Сериал удален", 
            "deleted_series": deleted_data
        })
        
        execution_time = time.time() - start_time
        update_statistics(f"DELETE /series/{series_id}", execution_time)
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics(f"DELETE /series/{series_id}", execution_time)
        logger.error(f"❌ Ошибка при удалении сериала {series_id}: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 6. ПРОВЕРКА СЕРВЕРА
@app.route('/health', methods=['GET'])
def health():
    start_time = time.time()
    logger.info("❤️ Проверка здоровья сервера")
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM series")
        series_count = cursor.fetchone()[0]
        db.close()
        
        # Проверяем Redis
        redis_client = get_redis()
        redis_status = "connected" if redis_client and redis_client.ping() else "disconnected"
        
        response = jsonify({
            "status": "OK", 
            "message": "Сервер работает нормально",
            "series_count": series_count,
            "redis": redis_status,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        execution_time = time.time() - start_time
        update_statistics("GET /health", execution_time)
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics("GET /health", execution_time)
        logger.error(f"❌ Ошибка при проверке здоровья: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 7. СТАТИСТИКА ВЫПОЛНЕНИЯ ЗАПРОСОВ
@app.route('/stats', methods=['GET'])
def get_stats():
    start_time = time.time()
    logger.info("📊 Запрос статистики выполнения")
    
    try:
        stats_summary = {
            'total_requests': request_stats['total_requests'],
            'average_execution_time_sec': round(request_stats['average_time'], 3),
            'endpoints': {}
        }
        
        for endpoint, endpoint_stat in request_stats['endpoints'].items():
            stats_summary['endpoints'][endpoint] = {
                'request_count': endpoint_stat['count'],
                'average_execution_time_sec': round(endpoint_stat['average_time'], 3),
                'min_execution_time_sec': round(endpoint_stat['min_time'], 3),
                'max_execution_time_sec': round(endpoint_stat['max_time'], 3)
            }
        
        # Добавляем статистику кэша
        redis_client = get_redis()
        if redis_client:
            try:
                cache_stats = {
                    'keys_count': len(redis_client.keys('*')),
                    'memory_usage': redis_client.info('memory')['used_memory_human']
                }
                stats_summary['cache'] = cache_stats
            except:
                stats_summary['cache'] = {'status': 'unavailable'}
        
        response = jsonify({
            "status": "success",
            "statistics": stats_summary,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        execution_time = time.time() - start_time
        update_statistics("GET /stats", execution_time)
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics("GET /stats", execution_time)
        logger.error(f"❌ Ошибка при получении статистики: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# 8. ГЛАВНАЯ СТРАНИЦА
@app.route('/', methods=['GET'])
def home():
    start_time = time.time()
    logger.info("🏠 Запрос главной страницы")
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM series")
        series_count = cursor.fetchone()[0]
        db.close()
        
        response = jsonify({
            "message": "Добро пожаловать в API турецких сериалов!",
            "total_series": series_count,
            "features": {
                "caching": "Redis кэширование включено",
                "database": "SQLite/PostgreSQL",
                "monitoring": "Статистика и логирование"
            },
            "endpoints": {
                "GET /series": "Получить все сериалы",
                "GET /series/<id>": "Получить один сериал",
                "POST /series": "Добавить сериал (требует Content-Type: application/json)",
                "PUT /series/<id>": "Обновить сериал (требует Content-Type: application/json)", 
                "DELETE /series/<id>": "Удалить сериал",
                "GET /health": "Проверить сервер",
                "GET /stats": "Статистика выполнения запросов"
            },
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        execution_time = time.time() - start_time
        update_statistics("GET /", execution_time)
        return response
        
    except Exception as e:
        execution_time = time.time() - start_time
        update_statistics("GET /", execution_time)
        logger.error(f"❌ Ошибка на главной странице: {str(e)}")
        return jsonify({"error": "Ошибка сервера"}), 500

# Обработчики ошибок
@app.errorhandler(404)
def not_found(error):
    logger.warning(f"🚫 Запрос к несуществующему маршруту: {request.path}")
    return jsonify({"error": "Маршрут не найден"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    logger.warning(f"🚫 Неподдерживаемый метод {request.method} для маршрута {request.path}")
    return jsonify({"error": "Метод не разрешен"}), 405

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК СЕРВЕРА ТУРЕЦКИХ СЕРИАЛОВ")
    
    # Получаем начальное количество сериалов
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM series")
    initial_count = cursor.fetchone()[0]
    db.close()
    
    # Проверяем Redis (теперь безопасно)
    try:
        redis_client = get_redis()
        redis_status = "✅ подключен" if redis_client else "❌ недоступен"
    except Exception as e:
        redis_status = f"❌ ошибка: {str(e)}"
    
    logger.info(f"📊 Начальное количество сериалов: {initial_count}")
    logger.info(f"🔴 Redis: {redis_status}")
    logger.info("📍 Сервер доступен по: http://localhost:5000")
    logger.info("=" * 50)
    
    print("✅ Сервер запущен! Тестируйте запросы:")
    print("1. GET  http://localhost:5000/")
    print("2. GET  http://localhost:5000/series") 
    print("3. GET  http://localhost:5000/series/1")
    print("4. POST http://localhost:5000/series")
    print("5. PUT  http://localhost:5000/series/1")
    print("6. DELETE http://localhost:5000/series/2")
    print("7. GET  http://localhost:5000/health")
    print("8. GET  http://localhost:5000/stats")
    print("-" * 50)
    print("📦 Redis кэширование: ВКЛЮЧЕНО")
    print("   - GET запросы кэшируются на 5 минут")
    print("   - POST/PUT/DELETE инвалидируют кэш")
    print("-" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)