import os
import datetime
import mimetypes
import secrets
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 初始化設定 ---
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = secrets.token_hex(16) 

# 初始化 Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
#  🛠️ 核心輔助函式：資料格式轉換 (翻譯機)
# ==========================================
def format_case(doc):
    data = doc.to_dict()
    
    # 處理時間：如果是 Datetime 物件轉字串，如果沒有則用現在時間
    created_at = data.get('createdAt') or data.get('reportTime')
    if isinstance(created_at, datetime.datetime):
        created_at = created_at.isoformat()
    
    return {
        "id": doc.id,
        # 1. 座標轉換：前端要 latitude/longitude，資料庫可能存 lat/lng
        "latitude": data.get('latitude') or data.get('lat') or 24.1446, 
        "longitude": data.get('longitude') or data.get('lng') or 120.6839,
        
        # 2. 欄位補全：確保欄位不為空
        "description": data.get('description', '無描述'),
        "category": data.get('category', 'other'),
        "severity": data.get('severity', 'normal'),
        "status": data.get('status', 'pending'),
        
        # 3. 圖片轉換：前端要 imageUrl，資料庫可能存 photoUrl
        "imageUrl": data.get('imageUrl') or data.get('photoUrl') or '',
        
        # 4. 報案人轉換：前端要 reporter，資料庫存 memberId
        "reporter": data.get('reporter') or data.get('memberId') or '訪客',
        
        "createdAt": created_at or datetime.datetime.now().isoformat(),

        # 5. ⭐️ 新增：評分與回饋欄位
        "rating": data.get('rating', 0),        # 評分 (1-5)
        "feedback": data.get('feedback', '')    # 文字回饋
    }

# ==========================================
#  1. 頁面路由
# ==========================================

@app.route('/')
def index():
    user = session.get('user') 
    return render_template('index.html', username=user)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    return render_template('dashboard.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/admin')
def admin_page():
    # 1. 先檢查有沒有登入
    if 'user' not in session:
        return redirect('/login')
    
    # 2. 檢查登入的人是不是 '333'
    if session['user'] != '333':
        # 如果不是，就顯示錯誤訊息
        return "<h1>⛔ 權限不足：您不是管理員</h1><p>此頁面僅限帳號 333 訪問</p><a href='/'>回首頁</a>", 403
        
    return render_template('admin.html')

@app.route('/crew')
def crew_page():
    # 1. 先檢查有沒有登入
    if 'user' not in session:
        return redirect('/login')

    # 2. 檢查登入的人是不是 '333'
    if session['user'] != '333':
        # 如果不是，就顯示錯誤訊息
        return "<h1>⛔ 權限不足：您不是維修人員</h1><p>此頁面僅限帳號 333 訪問</p><a href='/'>回首頁</a>", 403

    return render_template('crew.html')

# ==========================================
#  2. 使用者認證 API
# ==========================================

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        users_ref = db.collection('users')
        if any(users_ref.where('username', '==', username).stream()):
            return jsonify({"error": "帳號已存在"}), 400
        
        hashed_password = generate_password_hash(password)
        users_ref.document().set({
            'username': username, 'password': hashed_password, 'createdAt': datetime.datetime.now()
        })
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).stream()
        user_doc = None
        for doc in query: user_doc = doc.to_dict(); break
        
        if user_doc and check_password_hash(user_doc['password'], password):
            session['user'] = username
            return jsonify({"success": True}), 200
        else: return jsonify({"error": "帳號或密碼錯誤"}), 401
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# ==========================================
#  3. 案件與上傳 API
# ==========================================

@app.route('/api/reports', methods=['GET'])
def get_reports():
    try:
        try:
            docs = db.collection('cases').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        except Exception:
            docs = db.collection('cases').stream()
        
        # 使用 format_case 函式來統一格式
        reports = [format_case(doc) for doc in docs]
        
        return jsonify(reports), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/reports', methods=['POST'])
@app.route('/create_case', methods=['POST'])
def create_case():
    try:
        data = request.json
        # 統一儲存格式
        new_case = {
            'description': data.get('description'),
            'category': data.get('category', 'other'),
            'severity': data.get('severity', 'normal'),
            'latitude': data.get('latitude') or data.get('lat'),
            'longitude': data.get('longitude') or data.get('lng'),
            'imageUrl': data.get('imageUrl') or data.get('photoUrl'),
            'reporter': session.get('user', '訪客'),
            'memberId': session.get('user', '訪客'),
            'status': 'pending',
            'createdAt': datetime.datetime.now().isoformat()
        }
        
        doc_ref = db.collection('cases').document()
        doc_ref.set(new_case)
        return jsonify({"success": True, "id": doc_ref.id, "caseID": doc_ref.id}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/reports/<case_id>/status', methods=['PATCH'])
def update_status(case_id):
    try:
        data = request.json
        updates = {
            'status': data.get('status'),
            'updatedAt': datetime.datetime.now().isoformat()
        }
        if data.get('afterImageUrl'):
            updates['afterImageUrl'] = data.get('afterImageUrl')

        db.collection('cases').document(case_id).update(updates)
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ⭐️ 新增：使用者評分與回饋 API
@app.route('/api/reports/<case_id>/feedback', methods=['POST'])
def submit_feedback(case_id):
    try:
        data = request.json
        rating = data.get('rating')
        feedback = data.get('feedback')

        if not rating:
            return jsonify({"error": "請選擇評分星星"}), 400

        # 更新資料庫，加入評分資訊
        db.collection('cases').document(case_id).update({
            'rating': int(rating),
            'feedback': feedback,
            'ratedAt': datetime.datetime.now().isoformat()
        })
        
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        upload_folder = os.path.join(app.static_folder, 'uploads')
        if not os.path.exists(upload_folder): os.makedirs(upload_folder)
        
        if 'image' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        if file:
            filename = f"{datetime.datetime.now().timestamp()}_{file.filename}"
            file.save(os.path.join(upload_folder, filename))
            return jsonify({"url": f"/static/uploads/{filename}"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# 兼容舊後台 API (Assign Task)
@app.route('/assign_task', methods=['POST'])
def assign_task():
    try:
        data = request.json
        db.collection('cases').document(data.get('caseID')).update({
            'status': 'in_progress',
            'dedicatedUnitID': data.get('dedicatedUnitID'),
            'updatedAt': datetime.datetime.now().isoformat()
        })
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# 兼容舊後台 API (Process Case)
@app.route('/process_case', methods=['POST'])
def process_case():
    try:
        data = request.json
        db.collection('cases').document(data.get('caseID')).update({
            'status': 'completed',
            'resultDetails': data.get('resultDetails'),
            'completedAt': datetime.datetime.now().isoformat()
        })
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 伺服器啟動中: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)