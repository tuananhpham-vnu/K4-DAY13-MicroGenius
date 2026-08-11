from pathlib import Path

from app import logging_config
from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_passport_numbers() -> None:
    passport_numbers = ("B1234567", "AB123456")

    for passport_number in passport_numbers:
        out = scrub_text(f"So ho chieu: {passport_number}")
        assert passport_number not in out
        assert "REDACTED_PASSPORT" in out


def test_scrub_vietnamese_address() -> None:
    out = scrub_text("Toi song o 123 duong Nguyen Trai, Phuong Ben Thanh, Quan 1")
    assert "Nguyen Trai" not in out
    assert "Ben Thanh" not in out
    assert "REDACTED_ADDRESS_VN" in out


def test_scrub_does_not_flag_common_words_that_look_like_address_keywords() -> None:
    safe_sentences = (
        "Cau chuyen nay khong lien quan gi den dia chi ca",
        "Toi rat quan tam va quan trong voi viec nay",
        "Co quan lam viec cua toi rat xa nha",
    )

    for sentence in safe_sentences:
        assert scrub_text(sentence) == sentence


def test_end_to_end_scrubbing_removes_pii_from_log_file(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    logging_config.configure_logging()
    log = logging_config.get_logger()

    log.info(
        "request_received",
        service="api",
        payload={"message_preview": "Email test@example.com va SDT 0901234567"},
    )

    content = log_path.read_text(encoding="utf-8")
    assert "test@example.com" not in content
    assert "0901234567" not in content
    assert "REDACTED_EMAIL" in content
    assert "REDACTED_PHONE_VN" in content
