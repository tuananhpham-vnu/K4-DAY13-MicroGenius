# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: MicroGenius
- Repository URL: https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius
- Commit SHA cuối: `136645ff1d842c53e72bf71834409e8730e4d028` (merge PR #3, branch `role3`)
- Thành viên và vai trò:

| Thành viên | Phần việc |
|---|---|
| 2A202601226 Nguyễn Thị Thương | Thành viên B (Security & Compliance) — CP1: uncomment processor che PII, cấu hình regex patterns, mở rộng che PII toàn cục (passport, địa chỉ VN). |
| 2A202601788 Nguyễn Đức Anh | QA & Incident Analyst — chạy load test sinh dữ liệu, thiết kế Dashboard Spec, chủ trì điều tra Challenge (CP3), viết `REPORT.md`. |
| 2A202601838 Mai Tiến Dũng | Thành viên A (Logging & Middleware) — CP1: middleware, correlation ID, gán log metadata (bind_contextvars). |
| 2A202601070 Phạm Tuấn Anh | Thành viên C (Metrics & Alerting) — CP2: tích hợp Langfuse, đo `error_rate_pct`, viết SLO, alert rules và runbook. |

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: **100/100** — 104 log records, 0 record thiếu field bắt buộc, 0 record thiếu enrichment, 43 correlation ID duy nhất, 0 PII leak (ảnh [A-03](evidence/A-03-validate-logs.png), [B-02](evidence/B-02-validate-logs.png)).
- Tổng số traces: ≥ 51 root trace (`run`, ảnh [C-01](evidence/C-01-10-traces.png)); tổng quan sát bao gồm span con `retrieve`/`generate` đạt 366 (ảnh [C-02](evidence/C-02-dashboard-tracing.png)).
- Số PII leak còn lại: 0 (`validate_logs.py` — "Potential PII leaks detected: 0").
- Link/đường dẫn dashboard: Langfuse project `My Project` — `cloud.langfuse.com/project/cmsoct2jl00dfad0d8280qjs8`. Kết quả `python scripts/validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.`
  - Dashboard runtime: `data/dashboard.html`, sinh bằng `python scripts/build_dashboard.py` — đọc trực tiếp `data/logs.jsonl` và lấy panel/đơn vị/threshold từ `config/dashboard.yaml`, dùng cùng công thức percentile với `app/metrics.py` nên số liệu khớp endpoint `/metrics`. Đủ 6 panel (latency, traffic, errors, cost, tokens, quality), có time range 60 phút, auto refresh 30s và đường SLO: ảnh [D-02](evidence/D-02-dashboard-6panel.png) (baseline) và [D-07](evidence/D-07-dashboard-after.png) (sau incident).

## 3. Logging và tracing

- Evidence correlation ID: [A-01-response-correlation-id.png](evidence/A-01-response-correlation-id.png) — response header `x-request-id: req-demo-a123`, `x-response-time-ms: 3005.95`.
- Evidence PII redaction: [B-01-pii-redacted-log.png](evidence/B-01-pii-redacted-log.png) — `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_PASSPORT]`, `[REDACTED_ADDRESS_VN]` đều bị che trong `payload.message_preview`.
- Evidence trace waterfall: [C-02-dashboard-tracing.png](evidence/C-02-dashboard-tracing.png) — mỗi trace `run` có hai span con lồng bên dưới: `retrieve` (RAG) và `generate` (LLM), tổng cộng 322 `run` + 22 `retrieve` + 22 `generate` trong cửa sổ ảnh chụp.
- Giải thích một span đáng chú ý: Request với `correlation_id=req-demo-a123` ("Explain observability." / refund policy demo) có `latency_ms=3002` trong log JSON ([A-02](evidence/A-02-json-log-correlation-metadata.png)), khớp với `x-response-time-ms=3005.95` đo được ở phía client ([A-01](evidence/A-01-response-correlation-id.png)) — chứng minh correlation ID được truyền xuyên suốt từ response header vào log, và latency đo ở middleware khớp với latency thực đo bên ngoài. Trace tương ứng trên Langfuse cho thấy phần lớn thời gian nằm ở span `generate` (LLM), không phải `retrieve` — phù hợp với hành vi `FakeLLM.generate` có `time.sleep(0.15)` cộng dồn cùng token sinh ra nhiều hơn khi có incident `cost_spike`.

## 4. Prompt versioning

> ⚠️ *Phần này chưa có evidence trong `submission/evidence/` — cần hoàn thành theo `docs/PROMPT_VERSIONING.md` trước khi nộp bài.*

- Prompt name: `day13-chat`
- Version/label baseline: *(cần điền — tạo version 1, gắn label `baseline` + `production` trên Langfuse Prompt Management)*
- Version/label candidate: *(cần điền — tạo version 2 với thay đổi nhỏ về format/độ dài, gắn label `candidate`)*
- Trace ID của mỗi version: *(cần điền — chạy cùng input với `LANGFUSE_PROMPT_LABEL=baseline` và `candidate`, lấy 2 trace ID tương ứng)*
- Bằng chứng đổi label hoặc rollback: *(cần điền — chuyển `production` sang version 2, chạy lại 1 request, sau đó rollback `production` về version 1 và chụp ảnh trước/sau)*

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.`
- Evidence dashboard: [D-01](evidence/D-01-validate-dashboard.png) (kết quả validator), [D-02](evidence/D-02-dashboard-6panel.png) (dashboard baseline — cả 6 panel ĐẠT, p95 1,182ms), [D-07](evidence/D-07-dashboard-after.png) (sau incident — panel Latency chuyển đỏ VƯỢT NGƯỠNG 3,671ms, 5 panel còn lại vẫn ĐẠT).
- SLO đã chọn và lý do (`config/slo.yaml`, window 28 ngày):
  | SLI | Objective | Target | Lý do |
  |---|---|---|---|
  | `latency_p95_ms` | ≤ 3000ms | 99.5% | Khớp threshold panel Latency trong `dashboard.yaml`; đảm bảo trải nghiệm chat không bị cảm nhận là "treo". |
  | `error_rate_pct` | ≤ 2% | 99.0% | Khớp alert `elevated_error_rate` (cảnh báo ở 5%, SLO nghiêm ngặt hơn ở 2% để có buffer phát hiện sớm). |
  | `daily_cost_usd` | ≤ 2.5 | 100.0% | Khớp alert `cost_budget_exceeded`; ngân sách demo/lab cố định theo ngày, không cho phép vượt. |
  | `quality_score_avg` | ≥ 0.75 | 95.0% | Đảm bảo câu trả lời heuristic (`_heuristic_quality`) không bị suy giảm do PII redaction làm hỏng câu trả lời (`"[REDACTED"` bị trừ điểm quality). |
  - ⚠️ Lưu ý: `config/slo.yaml` hiện còn ghi chú mặc định `"Replace with your group's target"` ở `latency_p95_ms` — nhóm cần xác nhận lại giá trị 3000ms/99.5% là lựa chọn chính thức và xoá ghi chú TODO đó.
- Alert rules và runbook: 3 alert trong `config/alert_rules.yaml`, runbook đầy đủ trong `docs/alerts.md`:
  1. `high_latency_p95` (warning) — `latency_p95 > 3000ms` trong 5 phút, owner `on-call-engineer`.
  2. `elevated_error_rate` (critical) — `error_rate_pct > 5` trong 3 phút, owner `on-call-engineer`.
  3. `cost_budget_exceeded` (warning) — `daily_cost_usd > 2.5`, owner `team-lead`.

## 6. Điều tra challenge

> Challenge đã chạy: `python scripts/inject_incident.py` rồi `python scripts/load_test.py --challenge --concurrency 5`. Cả 5 request chính thức (`session_id` từ `k4-challenge-s01` đến `s05`) đều có trong `data/logs.jsonl`, và cả 5 đều vượt `latency_threshold_ms=2000`.

- Challenge ID: `day13-k4-observability-v1` (cohort `K4`, seed `1304`, theo `config/challenge.json`).
- Triệu chứng từ metrics: *(cần điền — kỳ vọng `latency_p95`/`latency_p99` tăng vượt `latency_threshold_ms=2000` ở feature `monitoring` sau khi chạy challenge, vì incident cấu hình sẵn là `rag_slow`)*.
- Trace ID liên quan: *(cần điền — lọc Langfuse theo `session_id` bắt đầu bằng `k4-challenge-`)*.
- Log line/correlation ID liên quan: *(cần điền — tìm trong `data/logs.jsonl` các record có `feature=monitoring` và `latency_ms` cao bất thường)*.
- Root cause: *(cần điền sau khi điều tra — giả thuyết ban đầu: span `retrieve` bị chậm do incident `rag_slow` giả lập `time.sleep(2.5)` trong `app/mock_rag.py:retrieve`)*.
- Fix action: *(cần điền — ví dụ tắt incident qua `POST /incidents/rag_slow/disable` hoặc tối ưu bước truy xuất tài liệu)*.
- Preventive measure: *(cần điền — ví dụ thêm alert `high_latency_p95` đã có sẵn ở mục 5 để phát hiện sớm tình huống tương tự trong tương lai)*.

## 7. Đóng góp cá nhân

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Mai Tiến Dũng | CP1 role A: Middleware, Correlation ID, gán log metadata | [`9aadabd`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/9aadabd) · PR [#1](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/pull/1) (merge [`6399bdd`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/6399bdd)) | Cách viết ASGI middleware (`BaseHTTPMiddleware`) để bọc mọi request; hiểu vì sao phải `clear_contextvars()` đầu mỗi request để tránh rò rỉ context giữa các request xử lý trên cùng worker; dùng correlation ID (`x-request-id`) làm "sợi chỉ" nối request ↔ response header ↔ log JSON, phục vụ truy vết end-to-end. |
| Nguyễn Thị Thương | CP1 role B: PII scrubbing processor, regex patterns, evidence | [`20b29d2`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/20b29d2) · PR [#2](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/pull/2) (merge [`49da4dd`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/49da4dd)) | Thiết kế regex pattern để nhận diện nhiều loại PII (email, SĐT VN, CCCD, thẻ tín dụng, passport, địa chỉ VN) và đánh đổi giữa che sót (false negative) và che nhầm (false positive); cách gắn một `structlog` processor vào đúng vị trí trong pipeline logging để nó chạy trên *mọi* field của log record chứ không chỉ riêng `payload`. |
| Phạm Tuấn Anh | CP2: Tích hợp Langfuse (spans `retrieve`/`generate`), `load_dotenv`, `error_rate_pct`, sửa bug `/chat` 500 (`body.model` → `agent.model`), Alert rules & Runbook | [`494e4cf`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/494e4cf) ("CP2") · PR [#3](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/pull/3) (merge [`136645f`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/136645f)) | Dùng decorator `@observe` của Langfuse để dựng trace waterfall lồng nhau (`run` → `retrieve`/`generate`) thay vì một span phẳng duy nhất; một biến môi trường "có trong `.env` nhưng không có `load_dotenv()`" vẫn coi như không tồn tại — luôn kiểm tra bằng `os.getenv()` thực tế thay vì tin vào file cấu hình; thiết kế alert theo triệu chứng (symptom-based, vd. `latency_p95`) chấm điểm tốt hơn alert theo nguyên nhân nội bộ; một lỗi tưởng như "kết nối mạng" (`WinError 10054`, JSON rỗng) thực chất bắt nguồn từ một `AttributeError` bị nuốt thành 500 ở tầng ứng dụng — luôn xem traceback gốc thay vì đoán ở tầng transport. |
| Nguyễn Đức Anh | QA & Incident Analyst: load test, Dashboard Spec, điều tra Challenge (CP3), viết `REPORT.md` | [`8fde40b`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/8fde40b) ("CP3") · PR [#5](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/pull/5) (merge [`ea3a75f`](https://github.com/tuananhpham-vnu/K4-DAY13-MicroGenius/commit/ea3a75f)) | Xây dashboard theo một "contract" (`config/dashboard.yaml`) trước rồi mới dựng chart giúp việc chấm điểm tự động (`validate_dashboard.py`) khách quan, không phụ thuộc công cụ dựng dashboard cụ thể; load test đồng thời (`--concurrency`) là cách nhanh nhất để tạo đủ dữ liệu baseline cho percentile latency (p50/p95/p99) thay vì gửi tuần tự từng request; quy trình điều tra incident chuẩn nên đi theo chiều metric (triệu chứng) → trace (định vị span chậm/lỗi) → log (giải thích root cause qua correlation ID), không đảo ngược thứ tự. |
