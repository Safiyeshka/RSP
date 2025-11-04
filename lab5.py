from flask import Flask, request, jsonify

app = Flask(__name__)

# Простая база данных в памяти
items = [
    {"id": 1, "name": "Пример предмета 1", "description": "Описание предмета 1"},
    {"id": 2, "name": "Пример предмета 2", "description": "Описание предмета 2"}
]
next_id = 3

# GET - получить все предметы
@app.route('/items', methods=['GET'])
def get_items():
    return jsonify(items)

# GET - получить предмет по ID
@app.route('/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = next((item for item in items if item['id'] == item_id), None)
    if item:
        return jsonify(item)
    return jsonify({"error": "Предмет не найден"}), 404

# POST - создать новый предмет
@app.route('/items', methods=['POST'])
def create_item():
    global next_id
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({"error": "Необходимо указать название предмета"}), 400
    
    new_item = {
        "id": next_id,
        "name": data['name'],
        "description": data.get('description', '')
    }
    
    items.append(new_item)
    next_id += 1
    return jsonify(new_item), 201

# PUT - обновить предмет
@app.route('/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.get_json()
    item = next((item for item in items if item['id'] == item_id), None)
    
    if not item:
        return jsonify({"error": "Предмет не найден"}), 404
    
    if 'name' in data:
        item['name'] = data['name']
    if 'description' in data:
        item['description'] = data['description']
    
    return jsonify(item)

# DELETE - удалить предмет
@app.route('/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    global items
    item = next((item for item in items if item['id'] == item_id), None)
    
    if not item:
        return jsonify({"error": "Предмет не найден"}), 404
    
    items = [item for item in items if item['id'] != item_id]
    return jsonify({"message": "Предмет удален"}), 200

if __name__ == '__main__':
    app.run(debug=True)