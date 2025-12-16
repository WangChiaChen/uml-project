import os
import datetime
import mimetypes
import secrets
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore

# --- 新增 Cloudinary import ---
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- 設定 Cloudinary (請去 Cloudinary Dashboard 複製你的資訊) ---
cloudinary.config( 
  cloud_name = "dm8ghtdnw", 
  api_key = "491181423841647", 
  api_secret = "UwZsq6Q8PahrTwiSSaIxIL-fKfw" 
)

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
        "latitude": data.get('latitude') or data.get('lat') or 24.1446, 
        "longitude": data.get('longitude') or data.get('lng') or 120.6839,
        "description": data.get('description', '無描述'),
        "category": data.get('category', 'other'),
        "severity": data.get('severity', 'normal'),
        "status": data.get('status', 'pending'),
        "imageUrl": data.get('imageUrl') or data.get('photoUrl') or '',
        "reporter": data.get('reporter') or data.get('memberId') or '訪客',
        "createdAt": created_at or datetime.datetime.now().isoformat(),
        "rating": data.get('rating', 0),
        "feedback": data.get('feedback', '')
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
    # 權限檢查：只限 333
    if 'user' not in session:
        return redirect('/login')
    
    if session['user'] != '333':
        return "<h1>⛔ 權限不足：您不是管理員</h1><p>此頁面僅限帳號 333 訪問</p><a href='/'>回首頁</a>", 403
        
    return render_template('admin.html')

@app.route('/crew')
def crew_page():
    # 權限檢查：只限 444
    if 'user' not in session:
        return redirect('/login')

    if session['user'] != '444':
        return "<h1>⛔ 權限不足：您不是維修人員</h1><p>此頁面僅限帳號 444 訪問</p><a href='/'>回首頁</a>", 403

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
        # 預設 isSuspended 為 False
        users_ref.document().set({
            'username': username, 
            'password': hashed_password, 
            'createdAt': datetime.datetime.now(),
            'isSuspended': False
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
        
        # 查詢使用者
        query = users_ref.where('username', '==', username).stream()
        user_doc = None
        
        for doc in query: 
            user_doc = doc.to_dict()
            # 將 ID 存起來備用，雖然這裡暫時用不到
            break
        
        if user_doc and check_password_hash(user_doc['password'], password):
            # 🛑 檢查是否被停權
            if user_doc.get('isSuspended', False) is True:
                return jsonify({"error": "此帳號已被停權，請聯繫管理員"}), 403

            session['user'] = username
            return jsonify({"success": True}), 200
        else: 
            return jsonify({"error": "帳號或密碼錯誤"}), 401
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
        
        reports = [format_case(doc) for doc in docs]
        return jsonify(reports), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/reports', methods=['POST'])
@app.route('/create_case', methods=['POST'])
def create_case():
    try:
        data = request.json
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

@app.route('/api/reports/<case_id>/feedback', methods=['POST'])
def submit_feedback(case_id):
    try:
        data = request.json
        rating = data.get('rating')
        feedback = data.get('feedback')

        if not rating:
            return jsonify({"error": "請選擇評分星星"}), 400

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
        # 檢查是否有檔案
        if 'image' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        if file:
            # --- 修改重點：直接上傳到 Cloudinary ---
            # Cloudinary 會自動處理檔案串流，不需要先存到本地
            upload_result = cloudinary.uploader.upload(file)
            
            # 取得安全的 HTTPS 網址
            image_url = upload_result.get('secure_url')
            
            # 回傳格式保持與原本一樣，這樣前端 index.html 不用改
            return jsonify({"url": image_url}), 200

    except Exception as e:
        print(f"上傳錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# 兼容舊後台 API
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

# ==========================================
#  4. 管理員帳號管理 API (新增)
# ==========================================

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    # 安全檢查：只有 333 可以看
    if session.get('user') != '333':
        return jsonify({"error": "權限不足"}), 403
        
    try:
        users = []
        docs = db.collection('users').stream()
        for doc in docs:
            u = doc.to_dict()
            users.append({
                "id": doc.id,
                "username": u.get('username'),
                "createdAt": u.get('createdAt'),
                "isSuspended": u.get('isSuspended', False)
            })
        return jsonify(users), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/suspend', methods=['POST'])
def suspend_user():
    # 安全檢查：只有 333 可以操作
    if session.get('user') != '333':
        return jsonify({"error": "權限不足"}), 403

    try:
        data = request.json
        user_id = data.get('userId')
        action = data.get('action') # 'suspend' or 'restore'
        
        is_suspended = True if action == 'suspend' else False
        
        db.collection('users').document(user_id).update({
            'isSuspended': is_suspended
        })
        
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 伺服器啟動中: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)