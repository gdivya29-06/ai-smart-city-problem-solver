import requests

BASE = "http://localhost:8000"

def test_health():
    r = requests.get(f"{BASE}/health")
    print(f"Status: {r.status_code}, Response: {r.text}")
    assert r.status_code == 200
    print("✅ Health check passed")

def test_create_complaint():
    with open("pothole.jpg", "rb") as img:
        r = requests.post(f"{BASE}/report",
            files={"image": ("pothole.jpg", img, "image/jpeg")},
            data={
                "issue": "pothole",
                "description": "Large pothole on Main Street causing accidents.",
                "location": "Main Street",
                "latitude": 28.6139,
                "longitude": 77.2090
            }
        )
    print(f"Status: {r.status_code}, Response: {r.text}")
    assert r.status_code == 200
    data = r.json()
    print(f"✅ Report issue passed — category: {data.get('category')}, severity: {data.get('severity')}, GPS: {data.get('latitude')}, {data.get('longitude')}")
    return data.get("id")

def test_list_complaints():
    r = requests.get(f"{BASE}/complaints")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    print(f"✅ List complaints passed — {data['total']} complaint(s) found")

def test_get_complaint(complaint_id):
    r = requests.get(f"{BASE}/complaints/{complaint_id}")
    assert r.status_code == 200
    print(f"✅ Get complaint passed — ID {complaint_id}")

def test_update_status(complaint_id):
    r = requests.patch(
        f"{BASE}/complaints/{complaint_id}/status",
        data={"status": "In Progress"}
    )
    print(f"Status: {r.status_code}, Response: {r.text}")
    assert r.status_code == 200
    print(f"✅ Update status passed")

def test_stats():
    r = requests.get(f"{BASE}/complaints/stats/summary")
    assert r.status_code == 200
    data = r.json()
    print(f"✅ Stats passed — total: {data.get('total')}")

def test_delete_complaint(complaint_id):
    r = requests.delete(f"{BASE}/complaints/{complaint_id}")
    assert r.status_code == 200
    print(f"✅ Delete complaint passed")

if __name__ == "__main__":
    print("Running API tests...\n")
    test_health()
    complaint_id = test_create_complaint()
    test_list_complaints()
    test_get_complaint(complaint_id)
    test_update_status(complaint_id)
    test_stats()
    test_delete_complaint(complaint_id)
    print("\n🎉 All tests passed!")