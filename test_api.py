import requests
import json

# 設定伺服器網址 (這是你剛剛 python app.py 跑起來的地方)
BASE_URL = "http://127.0.0.1:5000"

def run_test():
    print("🚀 開始系統測試...\n")

    # --- 1. 測試：民眾報案 (Create Case) ---
    print("Step 1: 民眾報案中...")
    report_data = {
        "description": "路面有一個大坑洞，機車經過很危險",
        "location": "台中市西屯區台灣大道三段",
        "photoUrl": "https://example.com/pothole.jpg",
        "memberId": "Member_001"
    }
    
    # 發送 POST 請求給你的 Flask 伺服器
    response = requests.post(f"{BASE_URL}/create_case", json=report_data)
    
    if response.status_code == 200:
        result = response.json()
        case_id = result.get("caseID")
        print(f"✅ 報案成功！案件編號 (Case ID): {case_id}")
    else:
        print(f"❌ 報案失敗: {response.text}")
        return # 失敗就停止測試

    print("-" * 30)

    # --- 2. 測試：分派任務 (Assign Task) ---
    print("Step 2: 初步接收單位正在分派任務...")
    assign_data = {
        "caseID": case_id,
        "dedicatedUnitID": "Unit_Road_Works" # 養工處
    }
    
    response = requests.post(f"{BASE_URL}/assign_task", json=assign_data)
    
    if response.status_code == 200:
        print(f"✅ 任務分派成功！案件狀態已更新為 Assigned")
    else:
        print(f"❌ 分派失敗: {response.text}")

    print("-" * 30)

    # --- 3. 測試：處理案件 (Process Case) ---
    print("Step 3: 專責單位正在回報處理結果...")
    process_data = {
        "caseID": case_id,
        "progressNotes": "工程車已抵達，開始填補",
        "resultDetails": "坑洞填補完成，路面已平整"
    }
    
    response = requests.post(f"{BASE_URL}/process_case", json=process_data)
    
    if response.status_code == 200:
        print(f"✅ 案件處理回報成功！系統已發送通知給報案人")
    else:
        print(f"❌ 處理回報失敗: {response.text}")

    print("\n🎉 測試結束！請去 Firebase 後台查看資料是否出現。")

if __name__ == "__main__":
    run_test()