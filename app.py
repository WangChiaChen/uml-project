import os
import datetime
import mimetypes
from flask import Flask, request, jsonify, render_template, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
# --- 2. 加入這兩行強制設定 (加在 app = Flask... 之前) ---
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

from flask import Flask, request, jsonify, render_template, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
# 初始化 Flask (指定 static 資料夾路徑)
app = Flask(__name__, static_folder='static', template_folder='templates')

# --- 初始化 Firebase ---
# 檢查是否已經初始化，避免重複執行錯誤
if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 輔助函式：轉換資料格式 ---
# 你的 React 前端使用 camelCase (如 createdAt)，但資料庫可能存不同格式
def format_case(doc):
    data = doc.to_dict()
    # 處理時間：如果是 Datetime 物件轉字串，如果沒有則用現在時間
    created_at = data.get('reportTime') or data.get('createdAt')
    if isinstance(created_at, datetime.datetime):
        created_at = created_at.isoformat()
    
    return {
        "id": doc.id,
        "latitude": data.get('location_lat', 0),   # 預設值，避免前端炸裂
        "longitude": data.get('location_lng', 0),
        "description": data.get('description', ''),
        "category": data.get('category', 'other'),
        "severity": data.get('severity', 'normal'),
        "status": data.get('status', 'pending'),
        "imageUrl": data.get('mediaFiles', [''])[0] if isinstance(data.get('mediaFiles'), list) and data.get('mediaFiles') else data.get('imageUrl', ''),
        "createdAt": created_at or datetime.datetime.now().isoformat()
    }

# --- 1. 路由設定：讓 React Router 接管頁面 ---
# 這段最重要！不管使用者輸入 /admin 還是 /report，都回傳 index.html
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    # 如果請求的是 API 或靜態檔案，不要回傳 HTML
    if path.startswith('api/') or path.startswith('static/'):
        return jsonify({"error": "Not Found"}), 404
    return render_template('index.html')

# --- 2. API: 取得所有案件 (對應 GET /api/reports) ---
@app.route('/api/reports', methods=['GET'])
def get_reports():
    try:
        cases_ref = db.collection('cases')
        docs = cases_ref.stream()
        reports = [format_case(doc) for doc in docs]
        return jsonify(reports), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- 3. API: 新增報案 (對應 POST /api/reports) ---
@app.route('/api/reports', methods=['POST'])
def create_report():
    try:
        data = request.json
        # 轉換前端傳來的資料格式
        new_case = {
            'description': data.get('description'),
            'category': data.get('category'),
            'severity': data.get('severity'),
            'location_lat': data.get('latitude'),
            'location_lng': data.get('longitude'),
            'status': 'pending',
            'reportTime': datetime.datetime.now(),
            'imageUrl': data.get('imageUrl'), # 存單張圖
            'mediaFiles': [data.get('imageUrl')] if data.get('imageUrl') else [] # 兼容舊格式
        }
        
        doc_ref = db.collection('cases').document()
        doc_ref.set(new_case)
        
        return jsonify({"success": True, "id": doc_ref.id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 4. API: 更新狀態 (對應 PATCH /api/reports/:id/status) ---
@app.route('/api/reports/<case_id>/status', methods=['PATCH'])
def update_status(case_id):
    try:
        data = request.json
        updates = {
            'status': data.get('status'),
            'lastUpdated': datetime.datetime.now()
        }
        # 如果有完工照片
        if data.get('afterImageUrl'):
            updates['afterImageUrl'] = data.get('afterImageUrl')

        case_ref = db.collection('cases').document(case_id)
        case_ref.update(updates)
        
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 5. API: 圖片上傳 (對應 POST /api/upload) ---
# 這裡做一個簡單的模擬上傳，因為你的 Replit 可能沒有連雲端儲存
@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        # 建立上傳資料夾
        upload_folder = os.path.join(app.static_folder, 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        if 'image' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file:
            # 為了簡單，直接用時間戳記當檔名
            filename = f"{datetime.datetime.now().timestamp()}_{file.filename}"
            file.save(os.path.join(upload_folder, filename))
            
            # 回傳網址
            file_url = f"/static/uploads/{filename}"
            return jsonify({"url": file_url}), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

    # -------------------------------------------
# API: 1. 民眾報案 (POST /create_case)
# -------------------------------------------
@app.route('/create_case', methods=['POST'])
def create_case_legacy():
    try:
        data = request.json

        new_case = {
            "description": data.get("description"),
            "location": data.get("location"),
            "photoUrl": data.get("photoUrl"),
            "memberId": data.get("memberId"),
            "status": "Reported",
            "createdAt": datetime.datetime.now(),
            "history": [
                {
                    "action": "Report Submitted",
                    "time": datetime.datetime.now(),
                    "detail": data.get("description")
                }
            ]
        }

        doc_ref = db.collection("cases").add(new_case)
        case_id = doc_ref[1].id

        return jsonify({"success": True, "caseID": case_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------
# API: 2. 初步接收單位分派 (POST /assign_task)
# -------------------------------------------
@app.route('/assign_task', methods=['POST'])
def assign_task():
    try:
        data = request.json
        case_id = data.get("caseID")

        updates = {
            "status": "Assigned",
            "assignedUnit": data.get("dedicatedUnitID"),
            "assignedAt": datetime.datetime.now(),
        }

        case_ref = db.collection("cases").document(case_id)
        case_ref.update(updates)

        # 更新歷史紀錄
        case_ref.update({
            "history": firestore.ArrayUnion([
                {
                    "action": "Task Assigned",
                    "unit": data.get("dedicatedUnitID"),
                    "time": datetime.datetime.now()
                }
            ])
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------
# API: 3. 回報處理結果 (POST /process_case)
# -------------------------------------------
@app.route('/process_case', methods=['POST'])
def process_case():
    try:
        data = request.json
        case_id = data.get("caseID")

        updates = {
            "status": "Completed",
            "progressNotes": data.get("progressNotes"),
            "resultDetails": data.get("resultDetails"),
            "completedAt": datetime.datetime.now()
        }

        case_ref = db.collection("cases").document(case_id)
        case_ref.update(updates)

        # 加入歷史紀錄
        case_ref.update({
            "history": firestore.ArrayUnion([
                {
                    "action": "Case Processed",
                    "notes": data.get("progressNotes"),
                    "result": data.get("resultDetails"),
                    "time": datetime.datetime.now()
                }
            ])
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
