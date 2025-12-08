import os
import json
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, g
import psycopg2
from psycopg2 import extras
import redis
from kafka import KafkaProducer
from kafka.errors import KafkaError

# ===== CONFIGURATION =====
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'postgres'),
    'database': os.getenv('DB_NAME', 'seriesdb'),  # Изменено с bookdb на seriesdb
    'user': os.getenv('DB_USER', 'user'),
    'password': os.getenv('DB_PASS', 'password')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'decode_responses': True
}

KAFKA_CONFIG = {
    'bootstrap_servers': [os.getenv('KAFKA_BROKER_HOST', 'kafka:9092')],
    'topic': os.getenv('KAFKA_TOPIC', 'series_events'),  # Изменено с book_events на series_events
    'dead_letter_topic': os.getenv('DEAD_LETTER_TOPIC', 'dead_letter_events')
}

# ===== LOGGING SETUP =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ===== GLOBAL SERVICES =====
redis_client = None
kafka_producer = None
dead_letter_producer = None

# ===== DATABASE CONNECTION =====
def get_db_connection():
    """Get database connection with retry logic"""
    if 'db_conn' not in g or g.db_conn.closed:
        max_retries = 10
        for attempt in range(max_retries):
            try:
                g.db_conn = psycopg2.connect(**DB_CONFIG)
                logger.info("✅ Database connection established")
                return g.db_conn
            except Exception as e:
                logger.warning(f"⚠️ Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2)
    return g.db_conn

@app.teardown_appcontext
def close_db_connection(exception):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        db_conn.close()

def init_kafka_producer(): 
    global kafka_producer, dead_letter_producer
    
    max_retries = 15
    for attempt in range(max_retries):
        try:
            kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_CONFIG['bootstrap_servers'],
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                acks='all',
                retries=3,
                request_timeout_ms=10000,
                api_version=(2, 0, 2)
            )
            
            dead_letter_producer = KafkaProducer(
                bootstrap_servers=KAFKA_CONFIG['bootstrap_servers'],
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8')
            )
            
            logger.info("Kafka producers initialized successfully")
            return True
            
        except Exception as e:
            logger.warning(f"Kafka producer attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error("Failed to initialize Kafka producers")
                return False
            time.sleep(3)

# ===== REDIS SETUP =====
def init_redis():
    """Initialize Redis connection"""
    global redis_client
    
    max_retries = 10
    for attempt in range(max_retries):
        try:
            redis_client = redis.Redis(**REDIS_CONFIG)
            redis_client.ping()
            logger.info("✅ Redis connection established")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error("❌ Failed to connect to Redis")
                redis_client = None
                return False
            time.sleep(2)

# ===== DATABASE INITIALIZATION =====
def init_database():
    """Initialize database tables and sample data"""
    max_retries = 10
    for attempt in range(max_retries):
        try:
            # Сначала подключаемся без указания базы данных
            temp_config = DB_CONFIG.copy()
            temp_config['database'] = 'postgres'  # Подключаемся к системной БД
            
            conn = psycopg2.connect(**temp_config)
            conn.autocommit = True
            with conn.cursor() as cursor:
                # Создаем базу данных если ее нет
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'seriesdb'")
                if not cursor.fetchone():
                    cursor.execute('CREATE DATABASE seriesdb')
                    logger.info("✅ Database 'seriesdb' created")
            
            conn.close()
            
            # Теперь подключаемся к нашей базе данных
            conn = psycopg2.connect(**DB_CONFIG)
            with conn.cursor() as cursor:
                # Create series table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS series (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        year INTEGER,
                        episodes INTEGER,
                        rating FLOAT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Insert sample data if table is empty
                cursor.execute("SELECT COUNT(*) FROM series")
                if cursor.fetchone()[0] == 0:
                    sample_series = [
                        ('Великолепный век', 2011, 139, 8.2),
                        ('Любовь напрокат', 2020, 52, 7.8),
                        ('Постучи в мою дверь', 2020, 52, 8.1),
                        ('Стамбульская невеста', 2023, 45, 7.9),
                        ('Вдребезги', 2022, 36, 8.4)
                    ]
                    cursor.executemany(
                        "INSERT INTO series (title, year, episodes, rating) VALUES (%s, %s, %s, %s)",
                        sample_series
                    )
                    logger.info(f"✅ Inserted {len(sample_series)} sample series")
                
                conn.commit()
            conn.close()
            logger.info("✅ Database initialized successfully")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Database initialization attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error("❌ Failed to initialize database")
                return False
            time.sleep(2)
   

# ===== KAFKA EVENT PUBLISHING =====
def publish_kafka_event(action, series_data=None, series_id=None):
    """Publish event to Kafka topic with error handling"""
    if not kafka_producer:
        logger.error("❌ Kafka producer not available")
        return False
    
    try:
        event = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user_ip': request.remote_addr,
            'series_id': series_id,  # Изменено с book_id на series_id
            'data': series_data      # Изменено с book_data на series_data
        }
        
        future = kafka_producer.send(KAFKA_CONFIG['topic'], value=event)
        future.get(timeout=10)
        
        logger.info(f"✅ Event published: {action} for series {series_id}")
        return True
        
    except KafkaError as e:
        logger.error(f"❌ Kafka error: {e}")
        send_to_dead_letter_queue(event, str(e))
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error publishing event: {e}")
        return False

def send_to_dead_letter_queue(event, error_message):
    """Send failed messages to dead letter queue"""
    if dead_letter_producer:
        try:
            dead_event = {
                **event,
                'error': error_message,
                'dead_letter_timestamp': datetime.now().isoformat()
            }
            dead_letter_producer.send(KAFKA_CONFIG['dead_letter_topic'], value=dead_event)
            logger.info("✅ Message sent to dead letter queue")
        except Exception as e:
            logger.error(f"❌ Failed to send to dead letter queue: {e}")

# ===== REQUEST STATISTICS =====
request_stats = {
    'total_requests': 0,
    'average_time': 0,
    'endpoints': {}
}

def update_statistics(endpoint, execution_time):
    """Update request statistics"""
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
    
    stats = request_stats['endpoints'][endpoint]
    stats['count'] += 1
    stats['total_time'] += execution_time
    stats['average_time'] = stats['total_time'] / stats['count']
    stats['min_time'] = min(stats['min_time'], execution_time)
    stats['max_time'] = max(stats['max_time'], execution_time)

# ===== REQUEST HOOKS =====
@app.before_request
def before_request():
    """Log incoming requests"""
    g.start_time = time.time()
    logger.info(f"📥 Incoming: {request.method} {request.path}")

@app.after_request
def after_request(response):
    """Log outgoing responses and update statistics"""
    execution_time = time.time() - g.start_time
    endpoint = f"{request.method} {request.path}"
    
    update_statistics(endpoint, execution_time)
    
    logger.info(f"📤 Outgoing: {response.status_code} for {endpoint} - {execution_time:.3f}s")
    return response

# ===== API ROUTES =====

@app.route('/')
def index():
    """API information"""
    return jsonify({
        'message': 'TV Series Library API with Kafka',
        'endpoints': {
            'GET /series': 'Get all series',
            'GET /series/<id>': 'Get series by ID',
            'POST /series': 'Create new series',
            'PUT /series/<id>': 'Update series',
            'DELETE /series/<id>': 'Delete series',
            'GET /stats': 'Get request statistics',
            'GET /health': 'Health check'
        }
    })

@app.route('/series', methods=['GET'])  # Изменено с /books на /series
def get_series():
    """Get all series with Redis caching"""
    cache_key = 'all_series'  # Изменено ключ кэша
    
    if redis_client:
        try:
            cached_series = redis_client.get(cache_key)
            if cached_series:
                logger.info("📺 Series retrieved from cache")
                return jsonify(json.loads(cached_series))
        except Exception as e:
            logger.warning(f"⚠️ Redis cache error: {e}")
    
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
            cursor.execute("SELECT id, title, year, episodes, rating FROM series ORDER BY id")
            series_list = cursor.fetchall()
        
        if redis_client:
            try:
                redis_client.setex(
                    cache_key,
                    int(os.getenv('REDIS_CACHE_TIMEOUT', 30)),
                    json.dumps([dict(series) for series in series_list], ensure_ascii=False)
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to cache in Redis: {e}")
        
        logger.info(f"📺 Retrieved {len(series_list)} series from database")
        return jsonify([dict(series) for series in series_list])
        
    except Exception as e:
        logger.error(f"❌ Error getting series: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/series/<int:series_id>', methods=['GET'])  # Изменено с books на series
def get_series_by_id(series_id):
    """Get series by ID"""
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, title, year, episodes, rating FROM series WHERE id = %s",
                (series_id,)
            )
            series = cursor.fetchone()
        
        if series:
            logger.info(f"📖 Retrieved series ID {series_id}")
            return jsonify(dict(series))
        else:
            logger.warning(f"❌ Series {series_id} not found")
            return jsonify({'error': 'Series not found'}), 404
            
    except Exception as e:
        logger.error(f"❌ Error getting series {series_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/series', methods=['POST'])  # Изменено с /books на /series
def create_series():
    """Create new series"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'JSON data required'}), 400
        
        required_fields = ['title', 'year', 'episodes', 'rating']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': f'Missing required fields: {required_fields}'
            }), 400
        
        conn = get_db_connection()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
            cursor.execute('''
                INSERT INTO series (title, year, episodes, rating)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, year, episodes, rating
            ''', (data['title'], data['year'], data['episodes'], data['rating']))
            
            new_series = cursor.fetchone()
            conn.commit()
        
        if redis_client:
            redis_client.delete('all_series')
        
        publish_kafka_event('series_created', dict(new_series), new_series['id'])
        
        logger.info(f"✅ Created series: {new_series['title']} (ID: {new_series['id']})")
        return jsonify(dict(new_series)), 201
        
    except Exception as e:
        logger.error(f"❌ Error creating series: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/series/<int:series_id>', methods=['PUT'])  # Изменено с books на series
def update_series(series_id):
    """Update series"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'JSON data required'}), 400
        
        conn = get_db_connection()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
            update_fields = []
            values = []
            
            for field in ['title', 'year', 'episodes', 'rating']:
                if field in data:
                    update_fields.append(f"{field} = %s")
                    values.append(data[field])
            
            if not update_fields:
                return jsonify({'error': 'No fields to update'}), 400
            
            values.append(series_id)
            query = f"""
                UPDATE series 
                SET {', '.join(update_fields)} 
                WHERE id = %s 
                RETURNING id, title, year, episodes, rating
            """
            
            cursor.execute(query, values)
            updated_series = cursor.fetchone()
            
            if not updated_series:
                return jsonify({'error': 'Series not found'}), 404
            
            conn.commit()
        
        if redis_client:
            redis_client.delete('all_series')
        
        publish_kafka_event('series_updated', dict(updated_series), series_id)
        
        logger.info(f"✅ Updated series ID {series_id}")
        return jsonify(dict(updated_series))
        
    except Exception as e:
        logger.error(f"❌ Error updating series {series_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/series/<int:series_id>', methods=['DELETE'])  # Изменено с books на series
def delete_series(series_id):
    """Delete series"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT title, year FROM series WHERE id = %s", (series_id,))
            series_info = cursor.fetchone()
            
            if not series_info:
                return jsonify({'error': 'Series not found'}), 404
            
            cursor.execute("DELETE FROM series WHERE id = %s", (series_id,))
            conn.commit()
        
        if redis_client:
            redis_client.delete('all_series')
        
        publish_kafka_event('series_deleted', {
            'title': series_info[0],
            'year': series_info[1]
        }, series_id)
        
        logger.info(f"✅ Deleted series ID {series_id}")
        return jsonify({'message': f'Series {series_id} deleted successfully'})
        
    except Exception as e:
        logger.error(f"❌ Error deleting series {series_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get request statistics"""
    return jsonify(request_stats)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {}
    }
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        status['services']['database'] = 'healthy'
    except Exception as e:
        status['services']['database'] = f'unhealthy: {e}'
        status['status'] = 'degraded'
    
    if redis_client:
        try:
            redis_client.ping()
            status['services']['redis'] = 'healthy'
        except Exception as e:
            status['services']['redis'] = f'unhealthy: {e}'
            status['status'] = 'degraded'
    else:
        status['services']['redis'] = 'not connected'
    
    if kafka_producer:
        try:
            test_future = kafka_producer.send(KAFKA_CONFIG['topic'], value={'test': 'health_check'})
            status['services']['kafka'] = 'healthy'
        except Exception as e:
            status['services']['kafka'] = f'unhealthy: {e}'
            status['status'] = 'degraded'
    else:
        status['services']['kafka'] = 'not connected'
    
    return jsonify(status)

# ===== ERROR HANDLERS =====
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ===== APPLICATION INITIALIZATION =====
def initialize_services():
    """Initialize all services"""
    logger.info("🚀 Initializing services...")
    
    init_database()
    init_redis()
    init_kafka_producer()
    
    logger.info("✅ All services initialized successfully")

if __name__ == '__main__':
    initialize_services()
    
    logger.info("""
    📺 TV Series Library API with Kafka
    ===================================
    Available endpoints:
    GET    /               - API information
    GET    /series         - Get all series
    GET    /series/<id>    - Get series by ID  
    POST   /series         - Create new series
    PUT    /series/<id>    - Update series
    DELETE /series/<id>    - Delete series
    GET    /stats          - Request statistics
    GET    /health         - Health check
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=False)