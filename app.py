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
# 設定 Session 密鑰
app.secret_key = secrets.token_hex(16) 

# 初始化 Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
#  1. 頁面路由
# ==========================================

@app.route('/')
def index():
    # ⭐️ 關鍵修改：將登入的使用者名稱傳給前端
    user = session.get('user') 
    return render_template('index.html', username=user)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    return render_template('dashboard.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

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
        
        reports = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            reports.append(data)
        return jsonify(reports), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/create_case', methods=['POST'])
def create_case():
    try:
        data = request.json
        # 分開儲存：地址 (字串) 與 座標 (數字)
        new_case = {
            'description': data.get('description'),
            'location': data.get('location'), # 中文地址
            'lat': data.get('lat'),
            'lng': data.get('lng'),
            'photoUrl': data.get('photoUrl'),
            'memberId': session.get('user', '匿名熱心民眾'),
            'status': 'New',
            'createdAt': datetime.datetime.now().isoformat()
        }
        
        doc_ref = db.collection('cases').document()
        doc_ref.set(new_case)
        return jsonify({"success": True, "caseID": doc_ref.id}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        upload_folder = os.path.join(app.static_folder, 'uploads')
        if not os.path.exists(upload_folder): os.makedirs(upload_folder)
        file = request.files['image']
        if file:
            filename = f"{datetime.datetime.now().timestamp()}_{file.filename}"
            file.save(os.path.join(upload_folder, filename))
            return jsonify({"url": f"/static/uploads/{filename}"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# 後台功能
@app.route('/assign_task', methods=['POST'])
def assign_task():
    try:
        data = request.json
        db.collection('cases').document(data.get('caseID')).update({
            'status': 'Assigned', 'dedicatedUnitID': data.get('dedicatedUnitID'), 'updatedAt': datetime.datetime.now().isoformat()
        })
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/process_case', methods=['POST'])
def process_case():
    try:
        data = request.json
        db.collection('cases').document(data.get('caseID')).update({
            'status': 'Completed', 'resultDetails': data.get('resultDetails'), 'completedAt': datetime.datetime.now().isoformat()
        })
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 伺服器啟動中: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)