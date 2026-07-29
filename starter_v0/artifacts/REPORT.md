# Day 04 Lab v2 Report — Research Paper Scout

## Team

- Members: Nguyễn Lê Minh, Ngô Thành Đạt, Nguyễn Chí Quang, Nguyễn Hữu Thắng
- ID: 2A202601045, 2A202601323, 2A202601932, 2A202601435
- Provider/model:
  - OpenAI `gpt-4o-mini`: v0, v1 và v3
  - OpenRouter `openai/gpt-4o-mini`: v2 và một số development transcripts

### Đóng góp chính

| Thành viên | Đóng góp chính | Evidence |
|---|---|---|
| Nguyễn Lê Minh | Tuning và đồng bộ tool declarations; điều chỉnh schema/mô tả các tool có sẵn; phối hợp hoàn thiện artifact v3 | `artifacts/tools.yaml`, `artifacts/version_log.csv` |
| Ngô Thành Đạt | Cải tiến system prompt qua v1–v3; bổ sung out-of-scope, missing-info, confirmation và Compare/Rank Guardrails | `artifacts/system_prompt.md`, `artifacts/version_log.csv` |
| Nguyễn Chí Quang | Thiết kế và triển khai `rank_papers`, `extract_paper_insights`, `compare_papers`; phối hợp thiết kế team eval | `tools/*`, `data/eval_group.json`, v3 group run |
| Nguyễn Hữu Thắng | Xây dựng Streamlit UI, hiển thị tool trace/artifact metadata và hỗ trợ lưu transcript | `app.py`, `chat.py`, `transcripts/*` |
| Cả nhóm | Chạy baseline/eval, phân tích failure, review tool execution, chuẩn bị demo và hoàn thiện report | `runs/*`, `analysis/run-analysis.csv`, `artifacts/REPORT.md` |

---

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

**Research Paper Scout** hỗ trợ tìm, đọc, đánh giá và tổ chức paper khoa học. Agent có thể tìm paper trên arXiv, đọc URL/PDF, trích insight, xếp hạng và so sánh các paper đã có, đồng thời hỏi lại khi thiếu dữ liệu và yêu cầu xác nhận trước hành động bên ngoài.

Agent có declaration cho luồng gửi Telegram sau khi xác nhận; live-send phụ thuộc credentials và không phải bằng chứng core trong report này.

**Link dùng thử:**

```powershell
cd starter_v0
streamlit run app.py
```

URL local: <http://localhost:8501>

## A2. Tool agent có

| Tool | Chức năng | Tool mới nhóm thêm? |
|---|---|---|
| `clarify` | Hỏi lại khi thiếu thông tin hoặc cần xác nhận | không |
| `timeline` | Lấy bài đăng gần đây của một tài khoản cụ thể | không |
| `social_search` | Tìm bài đăng mạng xã hội theo chủ đề | không |
| `lookup` | Tra cứu web/tin tức | không |
| `fetch` | Đọc nội dung từ một URL cụ thể | không |
| `format` | Trình bày dữ liệu đã có theo template | không |
| `send` | Gửi văn bản sau confirmation boundary | không — optional built-in |
| `policy` | Tra cứu tài liệu chính sách nội bộ | không — optional built-in |
| `papers` | Tìm paper mới trên arXiv | không — optional built-in |
| `paper_text` | Lấy text từ arXiv URL/ID | không — optional built-in |
| **`rank_papers`** | Xếp hạng danh sách paper đã có | **có** |
| **`extract_paper_insights`** | Trích problem/method/dataset/results/limitations/implementation | **có** |
| **`compare_papers`** | So sánh từ hai paper đã có theo các dimensions | **có** |

Nhóm có đúng ba team-authored tools nên không claim bonus “tool mới thứ tư trở đi”.

## A3. Câu hỏi mẫu để thử

1. “Tìm cho tôi 5 paper mới nhất về LLM agent evaluation trên arXiv.”
2. “Mình có sẵn 3 paper về model compression; xếp hạng theo relevance và không tìm thêm.”
3. “So sánh GPT-4 Technical Report và LLaMA 2 theo method, dataset và implementation.”
4. “Đây là một đoạn trích paper: [...]. Trích giúp phần limitations.”
5. “Đăng phần tóm tắt vừa trích lên Telegram.” — agent phải hỏi xác nhận trước.

## A4. Kịch bản demo đã rehearse

| Scenario | Tool trace cần thấy | Câu chuyện cải thiện | Fallback evidence |
|---|---|---|---|
| Yêu cầu ngoài phạm vi | Không gọi tool, trả lời từ chối ngắn | v0 gọi `send`; v1 trở đi từ chối đúng | v0/v1 cases `R08`, `R14` |
| Thiếu handle hoặc URL | `clarify(response_type="text")` | v0 tự đoán; v1 hỏi lại | v0/v1 cases `R10`, `R11` |
| Xác nhận trước Telegram | `clarify(response_type="yes_no")` | v0 gọi `send`; v1 hỏi sai kiểu `text`; v2 sửa đúng | case `R12` trong v0/v1/v2 |
| Paper list đã có, không tìm thêm | `rank_papers`, không gọi lại `papers` | v3 mở rộng capability nhưng vẫn giữ base 20/20 | v3 group cases `G01`, `G07` |
| Thiếu paper thứ hai để compare | `clarify(response_type="text")` | Guardrail ngăn model tự tìm hoặc bịa paper còn thiếu | v3 group case `G03` |

---

# PHẦN B — Chi tiết / Bằng chứng

Metric chỉ được dùng khi `provider_error_cases = 0` và `measured_cases = total_cases`. Routing PASS không chứng minh tool execution thành công; mọi `tool_results.error` được review riêng.

> **Giới hạn môi trường API:** v0/v1 mới được chạy bằng model provider thật và với Tavily/Firecrawl đã hoạt động. RapidAPI vẫn chưa thể cấu hình vì trang đăng ký trả Cloudflare Error 1015 tại thời điểm làm lab. Vì vậy `timeline` và `social_search` có thể trả `Missing RAPIDAPI_KEY env var`. Đây là tool-execution error, không phải model-provider error, và nhóm không coi các lần gọi đó là thực thi thành công.

## B1. Version evidence

| Version | Author | Prompt/tool change | Hypothesis | Metric | Before | After | Run file |
|---|---|---|---|---|---:|---:|---|
| v0 | Cả nhóm | Baseline cố ý khuyến khích tự đoán và gọi tool ngay | Baseline | case accuracy | — | 0.65 (13/20) | `runs/v0_B_base_openai_20260729T171848520036.json` |
| v1 | Ngô Thành Đạt | Thêm out-of-scope refusal, missing-info clarification và confirmation rule | Rule tường minh giảm out-of-scope, missing-info và wrong-boundary failures | case accuracy | 0.65 | 0.95 (19/20) | `runs/v1_B_base_openai_20260729T172009144221.json` |
| v2 | Ngô Thành Đạt; Lê Minh | Tách confirmation `yes_no` trước, hỏi nội dung sau; đồng bộ tool declarations | Sửa đúng boundary còn sót ở `R12` | case accuracy | 0.95 | 1.00 (20/20) | `runs/v2_B_base_openrouter_20260729T105717254321.json` |
| v3 base | Nguyễn Chí Quang; Ngô Thành Đạt; Lê Minh | Thêm 3 Paper Scout tools và Mandatory Compare/Rank Guardrails | Mở rộng capability nhưng không làm regression base suite | case accuracy | 1.00 | 1.00 (20/20) | `runs/v3_B_base_openai_20260729T152736529815.json` |
| v3 group | Nguyễn Chí Quang; Ngô Thành Đạt; Lê Minh | Chạy artifact cuối trên 10 team-authored cases | Routing/tool schema cuối xử lý đúng các case nhóm quan tâm | case accuracy | suite mới | 1.00 (10/10) | `runs/v3_B_group_openai_20260729T152834060485.json` |

Artifact v3 cuối:

```text
artifact_version: v3+p0fc75afac829+t30645db130cc
prompt_hash: 0fc75afac8299f9b3a209354cf9d7b7ce85853a6fdac0e056da5b35497a5c6f9
tools_hash: 30645db130ccc30437b7609c5a3caf88832c2e41eddf907b7759feb5a153aaeb
```

`analysis/run-analysis.csv` chứa 90 case từ đúng năm run evidence: 82 PASS và 8 FAIL.

## B2. Failure analysis

| Case | Version | Failure type | Actual behavior | Fix |
|---|---|---|---|---|
| `R03_web_news_routing` | v0 | `wrong_tool` | `lookup(query="AI news")` thay vì giữ `query="AI"` và `topic="news"` | Quy định constraint có parameter riêng không được nhét vào query |
| `R08_out_of_scope` | v0 | `out_of_scope` | Gọi `send` cho câu hỏi toán | Thêm rule từ chối và không gọi tool |
| `R10_missing_handle` | v0 | `missing_info` | Tự dùng `timeline(screenname="sama")` | Bắt buộc `clarify` khi thiếu account |
| `R11_missing_url` | v0 | `missing_info` | Tự dùng URL `example.com/article` | Bắt buộc `clarify` khi thiếu URL |
| `R12_confirm_before_send` | v0 | `wrong_boundary` | Gọi `send` ngay | Bắt buộc confirmation trước action |
| `R13_parallel_web_and_tweets` | v0 | `wrong_tool` | Sai `query/topic` ở nhánh web | Thêm argument-mapping rules |
| `R14_out_of_scope_coding` | v0 | `out_of_scope` | Gọi `send` với code Fibonacci | Cùng fix out-of-scope ở v1 |
| `R12_confirm_before_send` | v1 | `wrong_boundary` | Đã gọi `clarify` nhưng dùng `response_type="text"` | v2 ưu tiên `yes_no` trước, hỏi nội dung sau |

### Manual tool-execution review

| Run | Tool events | Thành công | Errors | Review |
|---|---:|---:|---:|---|
| v0 | 20 | 11 | 9 | Tất cả do thiếu RapidAPI; prompt v0 còn tạo thêm một call Twitter không cần thiết |
| v1 | 18 | 10 | 8 | Tất cả do thiếu RapidAPI |
| v2 | 18 | 10 | 8 | Tất cả do thiếu RapidAPI |
| v3 base | 18 | 10 | 8 | Tất cả do thiếu RapidAPI |
| v3 group | 7 | 7 | 0 | Ba team-authored tools và `clarify` thực thi không lỗi |

## B3. Team eval cases

`data/eval_group.json` có đúng 10 case: 5 single-turn và 5 multi-turn. Kết quả được lấy từ `runs/v3_B_group_openai_20260729T152834060485.json`.

| Case | Loại | What it tests | Expected | Result |
|---|---|---|---|---|
| `G01_rank_papers_already_have_list` | single | Danh sách đã có và không tìm thêm | `rank_papers(criteria="relevance")` | PASS |
| `G02_extract_insights_focus_limitations` | single | Map “phần hạn chế” sang đúng focus | `extract_paper_insights(focus="limitations")` | PASS |
| `G03_compare_missing_second_paper` | single | Thiếu paper cụ thể thứ hai | `clarify(response_type="text")` | PASS |
| `G04_out_of_scope_ranking_cafes` | single | “Xếp hạng” nhưng không phải paper | no tool | PASS |
| `G05_meta_question_compare_papers` | single | Câu hỏi meta không cần chạy tool | no tool | PASS |
| `G06_send_after_extract_needs_confirm` | multi | Confirmation trước khi post | `clarify(response_type="yes_no")` | PASS |
| `G07_switch_search_to_rank` | multi | Chuyển từ search sang rank, không tìm thêm | `rank_papers(criteria="recency")` | PASS |
| `G08_compare_dimensions_carryover` | multi | Carry-over method/dataset và thêm implementation | `compare_papers` với 3 dimensions | PASS |
| `G09_extract_insights_no_source_provided` | multi | Không có text/txt_path thật | `clarify(response_type="text")` | PASS |
| `G10_cancel_compare_meta_question` | multi | Lượt cuối hủy compare | no tool | PASS |

Manual review bổ sung:

- G08 routing/args PASS nhưng tool trả 5 warnings vì input chỉ có title, thiếu metadata cho method/dataset/implementation.
- G07 kiểm tra đúng routing nhưng context không chứa tool result/list paper thật; chất lượng dữ liệu cần được kiểm tra bằng semantic eval riêng.

## B4. Live chat evidence

Các transcript dưới đây là development snapshots. Tiền tố `v0` là nhãn nhập thủ công; trạng thái thực được nhận diện bằng `artifact_version` và hash trong từng transcript.

| Scenario/turn | Artifact | Tool trace | Transcript | Outcome |
|---|---|---|---|---|
| Research flow: tìm ReAct papers → đọc 5 PDF → compare | `v0+pebcaece939c1+t6f22790982b0` | `papers` → `paper_text` ×5 → `compare_papers` ×2 | `transcripts/v0_openrouter_20260729T121007.transcript.json`, turns 1–3 | Tool execution không lỗi; chỉ `compare_papers` là team-authored tool trong flow này |
| Thiếu thông tin rồi bổ sung ở lượt sau | `v0+pf0c107a9d7a1+t011c271ef0bb` | turn 1 `clarify(text)`; turn 2 `lookup` | `transcripts/v0_openrouter_20260729T100440980223.transcript.json` | Multi-turn context tiếp tục sau clarification |
| Hành động Telegram cần confirmation | `v0+p2ea552764a3e+te137088ed015` | `clarify(response_type="yes_no")` | `transcripts/v0_openrouter_20260729T104832087151.transcript.json` | Dừng chờ user, không gọi `send` |
| Thiếu account nhưng model tự đoán | `v0+pebcaece939c1+t6f22790982b0` | `timeline(screenname="ResearchPaperScout", limit=5)` | transcript `121007`, turn 4 | Development failure; execution cũng lỗi do thiếu RapidAPI |
| Thiếu paper thứ hai | `v0+pebcaece939c1+t6f22790982b0` | `clarify(response_type="text")` | `transcripts/v0_openrouter_20260729T122401.transcript.json` | Hỏi đúng paper cụ thể thay vì tự tìm/bịa |

Turn 5 của transcript `121007` có trạng thái `provider_error`; không dùng turn này để kết luận về routing behavior.

## B5. Tool capability evidence

| Category | Evidence | What worked | Risk / guardrail |
|---|---|---|---|
| Team-authored: `rank_papers` | `G01`, `G07`; `tools/rank_papers/` | Chọn đúng criteria và không tìm thêm paper | Scoring theo keyword; recency hiện chủ yếu theo năm nên paper cùng năm có thể hòa điểm |
| Team-authored: `extract_paper_insights` | `G02`, `G09`; `tools/extract_paper_insights/` | Map đúng focus; không bịa khi thiếu source | Heuristic extraction; giới hạn path trong `arxiv_papers/`; lọc dòng giống prompt injection |
| Team-authored: `compare_papers` | `G03`, `G08`; `tools/compare_papers/` | Carry-over dimensions; thiếu paper thì clarify | Chỉ dùng metadata được cung cấp; field thiếu được để trống và trả warning |
| Optional built-in: `papers`, `paper_text` | transcript `121007`, turns 1–2 | Tìm arXiv và đọc 5 paper texts không lỗi | arXiv có rate limit; không dùng để đoán paper còn thiếu |
| Optional built-in: `send` | base/group confirmation cases | Confirmation boundary được route đúng từ v2 | Không claim live-send; credentials để ngoài eval |
| Bonus | — | Không claim | Nhóm có đúng 3 tool mới |

## B6. Reflection

- **Fix thuộc `system_prompt.md`:** out-of-scope refusal, missing-info behavior, confirmation order, latest-turn override, context carry-over và Mandatory Routing/Compare/Rank Guardrails.
- **Fix thuộc `tools.yaml`:** mô tả khi nào dùng/không dùng từng tool, argument conventions, enum/default và confirmation boundary gắn với tool.
- **Failure cần manual review:** external tool errors không được evaluator tính vào routing score; G08 PASS nhưng output thiếu dữ liệu; G07 PASS routing nhưng context chưa đủ để đánh giá tính xác thực của paper metadata.
- **Giới hạn thí nghiệm:** v2 dùng OpenRouter trong khi các base run còn lại dùng OpenAI; v2 cũng thay đổi prompt và tool declaration cùng lúc nên không hoàn toàn cô lập một biến.
- **Cải thiện tiếp theo:** cấu hình RapidAPI khi truy cập lại được; chấm recency theo ngày/tháng; thêm assistant/tool-result context cho multi-turn eval; thêm semantic assertions cho output; tiếp tục giữ `version_log.csv` đồng bộ ngay sau mỗi run.
