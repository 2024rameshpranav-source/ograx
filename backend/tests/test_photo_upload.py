import io
import pytest

def test_photo_upload_valid_image(client):
    # Create small mock image in memory
    fake_image_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 200
    files = {"file": ("ground_evidence.jpg", io.BytesIO(fake_image_bytes), "image/jpeg")}
    
    resp = client.post("/api/reports/upload-photo", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert "photo_url" in data
    assert data["photo_url"].startswith("/uploads/report_photo_")
    assert data["content_type"] == "image/jpeg"
    assert data["size_bytes"] == len(fake_image_bytes)

    # Verify static file is served
    file_resp = client.get(data["photo_url"])
    assert file_resp.status_code == 200
    assert file_resp.content == fake_image_bytes

def test_photo_upload_invalid_mime_type(client):
    fake_txt_bytes = b"Hello, this is a plain text file, not an image."
    files = {"file": ("test.txt", io.BytesIO(fake_txt_bytes), "text/plain")}
    
    resp = client.post("/api/reports/upload-photo", files=files)
    assert resp.status_code == 400
    assert "Invalid image type" in resp.json()["detail"]

def test_photo_upload_oversized_image(client):
    # 5 MB + 1 KB = 5243880 bytes
    oversized_bytes = b"X" * (5 * 1024 * 1024 + 1024)
    files = {"file": ("giant.png", io.BytesIO(oversized_bytes), "image/png")}
    
    resp = client.post("/api/reports/upload-photo", files=files)
    assert resp.status_code == 413
    assert "exceeds maximum size limit" in resp.json()["detail"]

def test_report_creation_with_gps_and_photo(client):
    # 1. Upload photo
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 150
    files = {"file": ("waterlog_evidence.png", io.BytesIO(image_bytes), "image/png")}
    upload_resp = client.post("/api/reports/upload-photo", files=files)
    assert upload_resp.status_code == 201
    photo_url = upload_resp.json()["photo_url"]

    # 2. Submit report with GPS coordinates and photo URL
    report_payload = {
        "city": "Pune",
        "area": "Pune · Central Demonstration Area",
        "latitude": 18.52043,
        "longitude": 73.85674,
        "landmark": "Nal Stop Junction Underpass",
        "severity": "Severe",
        "description": "Live GPS captured report. Inundation up to 45cm blocking pedestrian and two-wheeler traffic.",
        "access": "Not passable",
        "coordinateSource": "gps",
        "accuracyM": 6.8,
        "photoUrl": photo_url
    }

    create_resp = client.post("/api/reports", json=report_payload)
    assert create_resp.status_code == 201
    report = create_resp.json()
    assert report["coordinateSource"] == "gps"
    assert report["accuracyM"] == 6.8
    assert report["photoUrl"] == photo_url
    assert report["city"] == "Pune"
    assert report["severity"] == "Severe"
    report_id = report["id"]

    # 3. Retrieve report by ID
    get_resp = client.get(f"/api/reports/{report_id}")
    assert get_resp.status_code == 200
    retrieved = get_resp.json()
    assert retrieved["coordinateSource"] == "gps"
    assert retrieved["accuracyM"] == 6.8
    assert retrieved["photoUrl"] == photo_url

    # 4. Verify listed in /api/reports query
    list_resp = client.get("/api/reports?city=Pune")
    assert list_resp.status_code == 200
    listed_items = list_resp.json()["reports"]
    matching = [r for r in listed_items if r["id"] == report_id]
    assert len(matching) == 1
    assert matching[0]["coordinateSource"] == "gps"
