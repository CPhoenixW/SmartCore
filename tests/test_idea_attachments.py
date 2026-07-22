from app.new_core import crud


def test_idea_attachment_url_matches_authorized_download_route() -> None:
    attachment = type("Attachment", (), {"attachmentId": "att-1", "fileName": "x.jpg", "mimeType": "image/jpeg", "sizeBytes": 1, "createdAt": "now"})()
    assert crud._attachmentDict(attachment)["url"] == "/api/idea/attachments/att-1"
