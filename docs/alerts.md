# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: high_latency_p95
- Severity: warning
- SLI/SLO liên quan: Latency SLO — p95 thời gian phản hồi `/chat` phải dưới 3000ms.
- Điều kiện và thời gian duy trì: `latency_p95 > 3000ms` trong 5 phút liên tiếp (đọc từ `GET /metrics`, field `latency_p95`).
- Ảnh hưởng tới người dùng: Người dùng phải chờ lâu bất thường để nhận câu trả lời, trải nghiệm chat bị giật/lag, có thể dẫn đến timeout ở phía client.
- Ba bước kiểm tra đầu tiên:
  1. Gọi `GET /metrics` để xác nhận `latency_p95`/`latency_p99` thực sự vượt ngưỡng (không phải nhiễu tạm thời).
  2. Kiểm tra trace mới nhất trên Langfuse để xem span nào (`retrieve` hay `generate`) đang chiếm phần lớn thời gian.
  3. Gọi `GET /health` để kiểm tra `incidents.rag_slow` — nếu `true` nghĩa là bước truy xuất tài liệu (RAG) đang bị chậm giả lập/thực tế.
- Mitigation tạm thời: Nếu `rag_slow` đang bật do incident giả lập, gọi `POST /incidents/rag_slow/disable` để tắt ngay. Nếu là sự cố thực tế ở vector store, cân nhắc bật cache câu trả lời gần nhất hoặc giảm timeout truy xuất để tránh nghẽn dây chuyền.
- Owner: on-call-engineer

## Alert 2

- Tên: elevated_error_rate
- Severity: critical
- SLI/SLO liên quan: Availability SLO — tỷ lệ request `/chat` trả lỗi (5xx) phải dưới 5%.
- Điều kiện và thời gian duy trì: `error_rate_pct > 5` trong 3 phút liên tiếp (đọc từ `GET /metrics`, field `error_rate_pct`).
- Ảnh hưởng tới người dùng: Một phần đáng kể request của người dùng bị lỗi, không nhận được câu trả lời (hiển thị lỗi hoặc không phản hồi).
- Ba bước kiểm tra đầu tiên:
  1. Gọi `GET /metrics` để xem `error_breakdown` — xác định loại lỗi (`error_type`) đang chiếm đa số.
  2. Tra log theo `correlation_id` của các request lỗi (event `request_failed`) trong `data/logs.jsonl` để đọc `detail`.
  3. Gọi `GET /health` để kiểm tra `incidents.tool_fail` — nếu `true` nghĩa là vector store đang bị giả lập timeout (`RuntimeError: Vector store timeout`).
- Mitigation tạm thời: Nếu `tool_fail` đang bật do incident giả lập, gọi `POST /incidents/tool_fail/disable` để tắt ngay. Nếu là sự cố thực tế, cân nhắc trả về fallback answer (bỏ qua bước RAG) trong khi chờ vector store phục hồi.
- Owner: on-call-engineer

## Alert 3

- Tên: cost_budget_exceeded
- Severity: warning
- SLI/SLO liên quan: Cost SLO — tổng chi phí LLM trong ngày không vượt ngân sách cho phép.
- Điều kiện và thời gian duy trì: `daily_cost_usd > 2.5` (đọc/tổng hợp từ `GET /metrics`, field `total_cost_usd`, theo dõi liên tục trong ngày — không cần cửa sổ thời gian ngắn vì đây là ngưỡng tích lũy).
- Ảnh hưởng tới người dùng: Không ảnh hưởng trực tiếp và tức thời tới trải nghiệm người dùng, nhưng nếu không xử lý có thể dẫn tới việc phải giới hạn/tắt tính năng để kiểm soát chi phí, ảnh hưởng gián tiếp tới khả năng phục vụ.
- Ba bước kiểm tra đầu tiên:
  1. Gọi `GET /metrics` để xem `total_cost_usd`, `tokens_in_total`, `tokens_out_total` — xác nhận mức tăng bất thường so với traffic (`traffic`).
  2. So sánh `avg_cost_usd` hiện tại với baseline lịch sử để xác định có phải do tăng token/response hay do tăng số lượng request.
  3. Gọi `GET /health` để kiểm tra `incidents.cost_spike` — nếu `true` nghĩa là response đang bị giả lập sinh ra nhiều token output hơn bình thường (x4).
- Mitigation tạm thời: Nếu `cost_spike` đang bật do incident giả lập, gọi `POST /incidents/cost_spike/disable` để tắt ngay. Nếu là sự cố thực tế, cân nhắc giới hạn `max_tokens` output hoặc tạm chuyển sang model rẻ hơn cho tới khi xác định nguyên nhân tăng chi phí.
- Owner: team-lead
