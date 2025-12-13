import os
import datetime
import mimetypes
import secrets # 用來產生密鑰
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash # 加密用
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 強制設定 MIME Types (解決白屏問題) ---
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

# 初始化 Flask
app = Flask(__name__, static_folder='static', template_folder='templates')

# --- 2. 設定 Session 密鑰 (登入功能必須) ---
#這行會產生一個隨機密碼來保護使用者的登入餅乾 (Cookie)
app.secret_key = secrets.token_hex(16) 

# --- 初始化 Firebase ---
if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 輔助函式 ---
def format_case(doc):
    data = doc.to_dict()
    created_at = data.get('reportTime') or data.get('createdAt')
    if isinstance(created_at, datetime.datetime):
        created_at = created_at.isoformat()
    
    return {
        "id": doc.id,
        "latitude": data.get('location_lat', 0),
        "longitude": data.get('location_lng', 0),
        "description": data.get('description', ''),
        "category": data.get('category', 'other'),
        "severity": data.get('severity', 'normal'),
        "status": data.get('status', 'pending'),
        "imageUrl": data.get('mediaFiles', [''])[0] if isinstance(data.get('mediaFiles'), list) and data.get('mediaFiles') else data.get('imageUrl', ''),
        "createdAt": created_at or datetime.datetime.now().isoformat()
    }

# ==========================================
#  🆕 新增：登入與註冊 API
# ==========================================

# 1. 顯示登入頁面
@app.route('/login')
def login_page():
    return render_template('login.html')

# 2. 註冊 API
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        # 檢查帳號是否已存在
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).stream()
        if any(query):
            return jsonify({"error": "帳號已存在"}), 400

        # 建立新帳號 (密碼加密)
        hashed_password = generate_password_hash(password)
        users_ref.document().set({
            'username': username,
            'password': hashed_password,
            'createdAt': datetime.datetime.now()
        })
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. 登入 API
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        # 搜尋使用者
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).stream()
        
        user_doc = None
        for doc in query:
            user_doc = doc.to_dict()
            break
        
        if user_doc and check_password_hash(user_doc['password'], password):
            # 登入成功：寫入 Session
            session['user'] = username
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "帳號或密碼錯誤"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. 登出 API (可選)
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

# ==========================================
#  原本的系統功能
# ==========================================

# --- 路由設定：加入登入檢查 ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    # 排除 API, Static, 和 Login 頁面
    if path.startswith('api/') or path.startswith('static/') or path == 'login':
        return jsonify({"error": "Not Found"}), 404
    
    # ⛔ 關鍵守門員：如果沒登入，強制踢去登入頁
    if 'user' not in session:
        return redirect('/login')

    return render_template('index.html')

@app.route('/api/reports', methods=['GET'])
def get_reports():
    # 只有登入才能看資料 (可選)
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        cases_ref = db.collection('cases')
        docs = cases_ref.stream()
        reports = [format_case(doc) for doc in docs]
        return jsonify(reports), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/reports', methods=['POST'])
def create_report():
    try:
        data = request.json
        new_case = {
            'description': data.get('description'),
            'category': data.get('category'),
            'severity': data.get('severity'),
            'location_lat': data.get('latitude'),
            'location_lng': data.get('longitude'),
            'status': 'pending',
            'reportTime': datetime.datetime.now(),
            'imageUrl': data.get('imageUrl'),
            'reporter': session.get('user', 'anonymous') # 紀錄是誰回報的
        }
        
        doc_ref = db.collection('cases').document()
        doc_ref.set(new_case)
        return jsonify({"success": True, "id": doc_ref.id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/reports/<case_id>/status', methods=['PATCH'])
def update_status(case_id):
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        updates = {'status': data.get('status'), 'lastUpdated': datetime.datetime.now()}
        if data.get('afterImageUrl'):
            updates['afterImageUrl'] = data.get('afterImageUrl')
        case_ref = db.collection('cases').document(case_id)
        case_ref.update(updates)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        upload_folder = os.path.join(app.static_folder, 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        if 'image' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        if file:
            filename = f"{datetime.datetime.now().timestamp()}_{file.filename}"
            file.save(os.path.join(upload_folder, filename))
            return jsonify({"url": f"/static/uploads/{filename}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)