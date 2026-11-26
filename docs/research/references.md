# Tài liệu tham khảo đã chốt

Ghi chú: đa số đọc qua abstract/tóm tắt; số liệu cần đối chiếu bản gốc trước khi đưa lên slide.

## Thiết kế multi-agent

| Nguồn | Ý chính | Dùng trong PayMatch |
|---|---|---|
| Kim et al., *Towards a Science of Scaling Agent Systems*, 2025 — https://arxiv.org/abs/2512.08296 | Agent độc lập khuếch đại lỗi 17,2×, có điều phối trung tâm còn 4,4×. Bài toán song song (Finance-Agent) +81%; bài toán tuần tự −39–70% | Có Kế toán trưởng; chuyên viên chạy song song |
| Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST), NeurIPS 2025 — https://arxiv.org/abs/2503.13657 | 14 kiểu hỏng, chủ yếu do thiết kế: vai mơ hồ, thiếu kiểm chứng | Mỗi bot một vai, output đúng schema `Finding` |
| Du et al., *Multiagent Debate*, ICML 2024 — https://proceedings.mlr.press/v235/du24e.html | Tranh luận tăng độ đúng, nhưng có thể hội tụ vào đáp án sai mà tự tin | Không dùng đồng thuận; gộp = mức nặng nhất |
| Xiao et al., *TradingAgents*, 2024 — https://arxiv.org/abs/2412.20138 | Mô phỏng công ty: analyst → trader → risk team → fund manager duyệt; output có cấu trúc + ngôn ngữ tự nhiên | Mẫu "tổ chức theo vai nghề"; chủ chuỗi là người duyệt cuối |
| Anthropic, *How we built our multi-agent research system*, 2025 — https://www.anthropic.com/engineering/multi-agent-research-system | Orchestrator-worker; brief rõ (mục tiêu, format, tool, ranh giới); tốn ~15× token | Brief cho mỗi chuyên viên; cache kết quả cho ngày chấm |
| xAI, Grok 4 Heavy — https://officechai.com/miscellaneous/elon-musk-explains-how-grok4-heavy-xais-multi-agent-reasoning-model-works/ | Nhiều agent làm độc lập rồi so kết quả | Chạy song song; nhưng gộp bất đối xứng |
| xAI, Grok Bot docs — https://docs.x.ai/grok-bot/how-grok-bot-works , /bots , /skills-routines-and-automations , /approvals-security-and-privacy | Bot (tên + việc + memory), Primary Bot điều phối, Skill, Routine, Template, approval card; *không* dùng bot làm ranh giới bảo mật; Auto Review dựa model "giảm nhưng không loại bỏ rủi ro" | Mượn Bot/Skill/Routine/Template; đảo ngược: bot **là** ranh giới quyền; chi tiền do code |

## Bảo mật agent

| Nguồn | Ý chính | Dùng trong PayMatch |
|---|---|---|
| Debenedetti et al., *CaMeL: Defeating Prompt Injections by Design*, 2025 — https://arxiv.org/abs/2503.18813 | Privileged LLM lập kế hoạch, quarantined LLM đọc dữ liệu bẩn không có tool; giá trị mang nhãn nguồn gốc | Kế toán trưởng = privileged; chuyên viên = quarantined; nhãn `trusted/untrusted` |
| *Can CaMeLs Talk?*, 2026 — https://arxiv.org/pdf/2610.05640 | Ghép nhiều agent an toàn vẫn bị tấn công khi nhãn nguồn bị mất qua ranh giới agent | Bot không nhắn trực tiếp nhau; nhãn nguồn đi theo mọi Finding |
| Beurer-Kellner et al., *Design Patterns for Securing LLM Agents*, 2025 — https://arxiv.org/abs/2506.08837 | Plan-then-execute, Dual LLM, ... | Kế hoạch điều tra cố định theo loại hóa đơn |
| Zhan et al., *InjecAgent*, ACL 2024 Findings — https://aclanthology.org/2024.findings-acl.624 ; Debenedetti et al., *AgentDojo*, NeurIPS 2024 | Agent vẫn bị lừa một phần số lần | Cách dựng ~36 ca thử; lý do bắt buộc có khóa code |

## Thanh toán do agent

| Nguồn | Ý chính | Dùng trong PayMatch |
|---|---|---|
| Google, *Agent Payments Protocol (AP2)*, 2025 — https://ap2-protocol.org/specification | Intent mandate → Cart mandate → Payment mandate, dựa W3C Verifiable Credentials | Mandate của chủ chuỗi + hóa đơn cụ thể → token trả một lần |
| *Whisper Attacks and a Binding Defense for AP2*, 2026 — https://arxiv.org/pdf/2609.11757 | Ký giao dịch nhưng không ký quyết định; đề xuất nonce dùng một lần xuyên các mandate | Token gắn (hóa đơn, người nhận, số tiền), dùng một lần |

Các nguồn khác (thị trường, pháp lý, đối thủ, P1–P10) xem Phụ lục A, C của [BRD](../01-requirements/PayMatch_BRD_v1.0.md).
