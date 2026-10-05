from .conftest import png_bytes


def upload(client, content=None, name="invoice_1042.png", doc_type=None):
    files = {"file": (name, content or png_bytes(), "image/png")}
    data = {"doc_type": doc_type} if doc_type else {}
    r = client.post("/api/documents", files=files, data=data)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_upload_process_review_edit_undo_export(client):
    doc_id = upload(client)
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "ready", doc.get("error_detail")
    assert doc["doc_type"] == "invoice"
    assert doc["version"]["number"] == 1
    assert doc["data"]["fields"]["total"]["value"] == "23600.00"
    assert doc["pages"][0]["url"].endswith("/pages/0")
    assert client.get(doc["pages"][0]["url"]).headers["content-type"] == "image/jpeg"
    assert client.get(doc["file_url"]).content.startswith(b"\x89PNG")  # original kept

    # Edit the vendor
    r = client.post(f"/api/documents/{doc_id}/operations", json={
        "operations": [{"op": "set_field", "field": "vendor", "value": "Acme Technologies"}],
        "base_version_id": doc["version"]["id"],
    })
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["data"]["fields"]["vendor"]["value"] == "Acme Technologies"
    assert doc["data"]["fields"]["vendor"]["confirmed"]
    assert doc["version"]["message"] == "Corrected vendor"
    assert doc["can_undo"] and not doc["can_redo"]

    # Stale base version is rejected
    r = client.post(f"/api/documents/{doc_id}/operations", json={
        "operations": [{"op": "set_field", "field": "vendor", "value": "X"}],
        "base_version_id": "stale",
    })
    assert r.status_code == 409

    # Undo / redo
    doc = client.post(f"/api/documents/{doc_id}/undo").json()
    assert doc["data"]["fields"]["vendor"]["value"] == "ABC Technologies Pvt Ltd"
    assert doc["can_redo"]
    doc = client.post(f"/api/documents/{doc_id}/redo").json()
    assert doc["data"]["fields"]["vendor"]["value"] == "Acme Technologies"

    # History keeps everything
    versions = client.get(f"/api/documents/{doc_id}/versions").json()["versions"]
    assert [v["number"] for v in versions] == [2, 1]
    v1 = versions[-1]["id"]
    doc = client.post(f"/api/documents/{doc_id}/versions/{v1}/restore").json()
    assert doc["version"]["number"] == 3 and doc["version"]["message"] == "Restored version 1"

    # Approve + export
    doc = client.post(f"/api/documents/{doc_id}/approve").json()
    assert doc["approved"]
    csv = client.get(f"/api/documents/{doc_id}/export.csv").text
    assert csv.startswith("﻿Field,Value")
    assert "Total,23600.00" in csv
    assert "Wireless Mouse,2,\"5,000.00\",\"10,000.00\"" in csv
    items = client.get(f"/api/documents/{doc_id}/export.csv?layout=line_items").text
    assert "ABC Technologies Pvt Ltd,INV-1042,2026-10-05,INR,Wireless Mouse" in items

    lib = client.get("/api/documents/export.csv").text
    assert "INV-1042" in lib


def test_assistant_proposes_but_does_not_apply(client):
    doc_id = upload(client)
    doc = client.get(f"/api/documents/{doc_id}").json()
    r = client.post(f"/api/documents/{doc_id}/assistant",
                    json={"message": "The vendor name is wrong. It's Acme Technologies."}).json()
    assert r["operations"] == [{"op": "set_field", "field": "vendor", "value": "Acme Technologies"}]
    assert r["preview"]["fields"][0]["after"] == "Acme Technologies"
    # Nothing changed until approved
    assert client.get(f"/api/documents/{doc_id}").json()["version"]["number"] == 1

    r = client.post(f"/api/documents/{doc_id}/assistant", json={"message": "Change the invoice date to October 4"}).json()
    assert r["operations"][0]["field"] == "invoice_date"
    assert r["preview"]["fields"][0]["after"] == "2026-10-04"

    table = doc["data"]["tables"][0]
    r = client.post(f"/api/documents/{doc_id}/assistant", json={"message": "split Rate into Unit and Price"}).json()
    assert r["operations"][0]["op"] == "split_column"
    after = r["preview"]["tables"][0]["after"]
    assert [c["name"] for c in after["columns"]] == ["Item", "Qty", "Unit", "Price", "Amount"]

    applied = client.post(f"/api/documents/{doc_id}/operations", json={
        "operations": r["operations"], "author": "ai", "base_version_id": doc["version"]["id"]}).json()
    assert applied["version"]["message"].startswith("Split “Rate”")
    assert len(applied["data"]["tables"][0]["columns"]) == len(table["columns"]) + 1


def test_type_mismatch_warning_and_switch(client):
    client.use_receipt()
    doc_id = upload(client, doc_type="invoice", name="cafe.png")
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["doc_type"] == "invoice"
    assert doc["classification"]["detected_type"] == "receipt"
    assert doc["classification"]["mismatch"] is True

    doc = client.post(f"/api/documents/{doc_id}/type", json={"doc_type": "receipt"}).json()
    assert doc["doc_type"] == "receipt"
    assert doc["data"]["fields"]["merchant"]["value"] == "CORNER CAFE"
    assert doc["classification"]["mismatch"] is False
    assert doc["version"]["number"] == 2


def test_duplicate_upload_flagged_not_deleted(client):
    content = png_bytes(color=(250, 250, 250))
    first = upload(client, content)
    second = client.post("/api/documents", files={"file": ("again.png", content, "image/png")}).json()
    assert second["duplicate_of"][0]["id"] == first
    docs = client.get("/api/documents").json()["documents"]
    assert len(docs) == 2


def test_rejects_unsupported_files(client):
    r = client.post("/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_search_and_filters(client):
    upload(client)
    assert len(client.get("/api/documents?q=inv-1042").json()["documents"]) == 1
    assert len(client.get("/api/documents?q=nothing-like-this").json()["documents"]) == 0
    assert len(client.get("/api/documents?type=invoice").json()["documents"]) == 1
    assert client.get("/api/documents/stats").json()["processed_today"] == 1
