from __future__ import annotations

import hashlib
import re

PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "cccd": r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    # Hộ chiếu VN: mẫu hiện hành (1 chữ + 7 số, vd B1234567) và mẫu cũ (2 chữ + 6 số, vd AB123456)
    "passport": r"\b[A-Z]\d{7}\b|\b[A-Z]{2}\d{6}\b",
    # Địa chỉ VN: số nhà + tên đường/ngõ/hẻm, hoặc phường/quận/huyện/thành phố kèm tên riêng
    # (nhận cả bản có dấu và không dấu, vì chat tiếng Việt thường gõ không dấu)
    "address_vn": (
        r"(?:[Ss][ốo]\s*)?\d+[A-Za-z0-9/]*\s+(?:đường|Đường|duong|Duong|phố|Phố|pho|Pho|ngõ|Ngõ|ngo|Ngo|hẻm|Hẻm|hem|Hem)\s+[^\n,.;]{2,40}"
        r"|(?:[Pp]hường|[Pp]huong|[Xx]ã|[Qq]uận|[Qq]uan|[Hh]uyện|[Hh]uyen|[Tt]hành phố|[Tt]hanh pho|TP\.?)\s+(?=[A-Z0-9À-Ỹ])[^\n,.;]{1,30}"
    ),
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
