"""One-off helper for docs/PROMPT_VERSIONING.md.

Tao (hoac tai su dung) 2 version cua prompt `day13-chat` tren Langfuse,
goi 1 ham duoc @observe theo tung label (baseline/candidate), chuyen
label `production` sang candidate, roi rollback ve baseline. In va luu
lai trace ID de dan vao submission/REPORT.md.

Usage:
    python scripts/prompt_versioning_demo.py
    # hoac, de tai su dung version prompt da tao san tren Langfuse:
    python scripts/prompt_versioning_demo.py --v1-version 1 --v2-version 2

Luu y: khong hardcode LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY trong file
nay. Key duoc doc tu .env (khong commit len git) qua load_dotenv().
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from langfuse import Langfuse, observe

langfuse = Langfuse()

PROMPT_NAME = "day13-chat"
PROMPT_TEXT_V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
PROMPT_TEXT_V2 = (
    "Feature={{feature}}\n"
    "Docs={{docs}}\n"
    "Question={{message}}\n"
    "Answer in at most 3 concise sentences."
)
DEMO_DOCS = "Refunds are available within 7 days with proof of purchase."
DEMO_MESSAGE = "What is your refund policy?"


def ensure_prompt_versions(v1_version: int, v2_version: int):
    if v1_version and v2_version:
        v1 = langfuse.get_prompt(PROMPT_NAME, version=v1_version, cache_ttl_seconds=0)
        v2 = langfuse.get_prompt(PROMPT_NAME, version=v2_version, cache_ttl_seconds=0)
        print("Tai su dung v1:", v1.name, v1.version, v1.labels)
        print("Tai su dung v2:", v2.name, v2.version, v2.labels)
        langfuse.update_prompt(name=PROMPT_NAME, version=v1.version, new_labels=["baseline", "production"])
    else:
        v1 = langfuse.create_prompt(
            name=PROMPT_NAME,
            prompt=PROMPT_TEXT_V1,
            labels=["baseline", "production"],
            type="text",
            commit_message="v1 baseline - original 3-variable template",
        )
        print("Da tao v1:", v1.name, v1.version, v1.labels)

        v2 = langfuse.create_prompt(
            name=PROMPT_NAME,
            prompt=PROMPT_TEXT_V2,
            labels=["candidate"],
            type="text",
            commit_message="v2 candidate - constrain answer to 3 sentences",
        )
        print("Da tao v2:", v2.name, v2.version, v2.labels)
    return v1, v2


@observe(as_type="generation")
def tra_loi_khach_hang(label: str, tag: str) -> dict | None:
    os.environ["LANGFUSE_PROMPT_LABEL"] = label
    print(f"\nDang tai prompt '{PROMPT_NAME}' voi label='{label}' tu Langfuse Cloud ve...")
    try:
        prompt = langfuse.get_prompt(PROMPT_NAME, label=label, type="text", cache_ttl_seconds=0)
    except Exception as exc:
        print(f"\nLOI: Khong tim thay prompt '{PROMPT_NAME}' voi label '{label}' tren Langfuse!")
        print("Ban chua tao prompt hoac chua gan nhan tren giao dien Web.", exc)
        return None

    cau_lenh_hoan_chinh = prompt.compile(feature="qa", docs=DEMO_DOCS, message=DEMO_MESSAGE)
    print("Kich ban hoan chinh (AI se nhan duoc):")
    print("--------------------------------------------------")
    print(cau_lenh_hoan_chinh)
    print("--------------------------------------------------")

    cau_tra_loi_cua_ai = (
        "Starter answer. Teams should improve this output logic and add better quality checks. "
        "Use retrieved context and keep responses concise."
    )

    # Ghi nhan vao trace hien tai (duoc tao tu dong boi @observe)
    langfuse.update_current_trace(
        name=f"prompt-demo-{tag}",
        session_id=f"prompt-demo-{tag}",
        user_id=f"prompt-demo-{tag}",
        tags=["prompt-versioning-demo", label],
    )
    langfuse.update_current_generation(
        prompt=prompt,
        usage_details={"prompt_tokens": 30, "completion_tokens": 15},
    )

    trace_id = langfuse.get_current_trace_id()
    trace_url = langfuse.get_trace_url(trace_id=trace_id) if trace_id else None
    return {
        "label": label,
        "prompt_version": prompt.version,
        "answer": cau_tra_loi_cua_ai,
        "trace_id": trace_id,
        "trace_url": trace_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-version", type=int, default=0, help="Tai su dung baseline version da co thay vi tao moi")
    parser.add_argument("--v2-version", type=int, default=0, help="Tai su dung candidate version da co thay vi tao moi")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "prompt_versioning_result.json")
    args = parser.parse_args()

    assert langfuse.auth_check(), "Langfuse auth failed - kiem tra LANGFUSE_* trong .env"
    print("Auth OK")

    v1, v2 = ensure_prompt_versions(args.v1_version, args.v2_version)

    results = {}

    print("\n--- Goi voi label=baseline ---")
    results["baseline"] = tra_loi_khach_hang("baseline", "baseline")

    print("\n--- Goi voi label=candidate ---")
    results["candidate"] = tra_loi_khach_hang("candidate", "candidate")

    print("\n--- Chuyen production sang v2 ---")
    langfuse.update_prompt(name=PROMPT_NAME, version=v2.version, new_labels=["candidate", "production"])
    time.sleep(1)
    prod = langfuse.get_prompt(PROMPT_NAME, label="production", cache_ttl_seconds=0)
    print("production hien la ->", prod.name, prod.version, prod.labels)

    print("\n--- Goi voi label=production (ky vong la v2) ---")
    results["production_v2"] = tra_loi_khach_hang("production", "prod-v2")

    print("\n--- Rollback production ve v1 ---")
    langfuse.update_prompt(name=PROMPT_NAME, version=v1.version, new_labels=["baseline", "production"])
    time.sleep(1)
    prod = langfuse.get_prompt(PROMPT_NAME, label="production", cache_ttl_seconds=0)
    print("production hien la ->", prod.name, prod.version, prod.labels)

    print("\n--- Goi voi label=production (ky vong la v1 sau rollback) ---")
    results["production_rollback"] = tra_loi_khach_hang("production", "prod-rollback")

    print("\nDang gui not (flush) len Langfuse...")
    langfuse.flush()

    summary = {
        "v1": {"version": v1.version, "labels": v1.labels},
        "v2": {"version": v2.version, "labels": v2.labels},
        "runs": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nDa luu ket qua vao", args.out)
    print("Xong! Hay mo Web Langfuse (tab Traces / Prompts) len xem ket qua.")


if __name__ == "__main__":
    main()
