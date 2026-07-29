from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from chat import (
    ARTIFACTS_DIR,
    ROOT,
    build_artifact_version,
    now_iso,
    run_model_tool_loop,
    safe_slug,
    write_transcript,
)
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict

load_lab_env(ROOT)
TRANSCRIPTS_DIR = ROOT / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_data
def load_transcripts(directory: Path) -> list[dict[str, Any]]:
    transcripts: list[dict[str, Any]] = []
    if not directory.exists():
        return transcripts
    for path in sorted(directory.glob("*.transcript.json"), reverse=True):
        try:
            transcript = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        transcripts.append(transcript)
    return transcripts


def build_scenario_key(transcript: dict[str, Any]) -> str:
    turns = transcript.get("turns", [])
    if not turns:
        return "<unknown scenario>"
    first_user = turns[0].get("user")
    return first_user or "<empty request>"


def display_rounds(rounds: list[dict[str, Any]]) -> None:
    for round_record in rounds:
        with st.container(border=True):
            st.markdown(f"**🔄 Round {round_record['round']}**")
            
            if round_record.get("assistant_text"):
                with st.chat_message("assistant"):
                    st.write(round_record.get("assistant_text", ""))
                    
            if round_record.get("tool_calls"):
                for tool_call in round_record["tool_calls"]:
                    with st.expander(f"🛠️ Đang gọi công cụ: `{tool_call['name']}`", expanded=False):
                        st.json(tool_call["args"])
                        
            if round_record.get("tool_results"):
                for event in round_record["tool_results"]:
                    tool = event.get("tool")
                    result = event.get("result")
                    has_error = isinstance(result, dict) and result.get("error")
                    status_text = "❌ Thất bại" if has_error else "✅ Thành công"
                    summary = f"{tool} — {status_text}"
                    
                    with st.expander(summary, expanded=has_error):
                        if has_error:
                            st.error(result)
                        else:
                            st.json(result)


def display_transcript_summary(transcript: dict[str, Any]) -> None:
    metadata = {
        "Transcript ID": transcript.get("transcript_id"),
        "Artifact version": transcript.get("artifact_version"),
        "Version": transcript.get("version"),
        "Provider": transcript.get("provider"),
        "Model": transcript.get("model"),
        "System prompt": transcript.get("system_prompt"),
        "Tools": transcript.get("tools"),
        "History window": transcript.get("history_window"),
        "Max tool rounds": transcript.get("max_tool_rounds"),
        "Created at": transcript.get("created_at"),
        "Updated at": transcript.get("updated_at"),
    }
    
    st.markdown("#### Thông tin cấu hình")
    cols = st.columns(3)
    for index, (label, value) in enumerate(metadata.items()):
        col = cols[index % 3]
        col.markdown(f"**{label}**")
        col.caption(f"{value}")

    if transcript.get("turns"):
        turn = transcript["turns"][0]
        st.markdown("---")
        st.markdown("#### Chi tiết lượt chạy (Turn Summary)")
        st.json({
            "turn_index": turn.get("turn_index"),
            "status": turn.get("status"),
            "started_at": turn.get("started_at"),
            "ended_at": turn.get("ended_at"),
        })


def main() -> None:
    st.set_page_config(page_title="Research Agent UI", page_icon="🤖", layout="wide")
    
    # ------------------ SIDEBAR ------------------
    st.sidebar.title("⚙️ Cấu hình Agent")
    provider_name = st.sidebar.selectbox("Provider", ["openrouter", "openai", "anthropic", "gemini"], index=0)
    selected_model = st.sidebar.text_input("Model (optional)", placeholder="e.g. gpt-4-turbo")
    version = st.sidebar.text_input("Artifact version", "v0")
    
    with st.sidebar.expander("🛠️ Cấu hình nâng cao", expanded=False):
        system_prompt_path = st.text_input("System prompt file", str(ARTIFACTS_DIR / "system_prompt.md"))
        tools_path = st.text_input("Tools declaration file", str(ARTIFACTS_DIR / "tools.yaml"))
        max_tool_rounds = st.number_input("Max tool rounds", min_value=1, max_value=10, value=4)
        history_window = st.number_input("History window", min_value=0, max_value=20, value=5)

    transcripts = load_transcripts(TRANSCRIPTS_DIR)
    scenario_to_transcripts: dict[str, list[dict[str, Any]]] = {}
    for transcript in transcripts:
        scenario_key = build_scenario_key(transcript)
        scenario_to_transcripts.setdefault(scenario_key, []).append(transcript)

    st.sidebar.markdown("---")
    if transcripts:
        with st.sidebar.expander("📊 Lịch sử & So sánh kịch bản", expanded=True):
            scenario = st.selectbox("Chọn kịch bản (Scenario)", sorted(scenario_to_transcripts.keys()))
            selected_transcripts = scenario_to_transcripts.get(scenario, [])
            if selected_transcripts:
                table = [
                    {
                        "Transcript": t.get("transcript_id")[:8] + "...", 
                        "Version": t.get("version"),
                        "Provider": t.get("provider"),
                        "Status": t.get("turns", [{}])[0].get("status"),
                    }
                    for t in selected_transcripts
                ]
                st.dataframe(table, use_container_width=True, hide_index=True)
            else:
                st.info("Chưa có transcripts cho kịch bản này.")
    else:
        st.sidebar.info("Chưa có lịch sử chạy. Hãy thực thi một yêu cầu để lưu.")

    # ------------------ MAIN UI ------------------
    st.title("🤖 Research Agent Workspace")
    st.markdown("Nhập câu hỏi hoặc tác vụ nghiên cứu để Agent bắt đầu quá trình suy luận và gọi công cụ.")

    # Request Box
    with st.container(border=True):
        user_request = st.text_area("Yêu cầu của bạn:", height=150, placeholder="Nhập câu hỏi tại đây...")
        
        col_btn, col_metric = st.columns([1, 4])
        with col_btn:
            run_btn = st.button("Chạy Yêu Cầu", type="primary", use_container_width=True)

    if run_btn:
        if not user_request.strip():
            st.warning("⚠️ Vui lòng nhập nội dung yêu cầu trước khi chạy.")
        else:
            system_prompt = Path(system_prompt_path)
            tools_file = Path(tools_path)
            
            if not system_prompt.exists() or not tools_file.exists():
                st.error("❌ Không tìm thấy file System prompt hoặc Tools. Vui lòng kiểm tra lại đường dẫn.")
            else:
                try:
                    system_prompt_text = system_prompt.read_text(encoding="utf-8")
                    tool_declarations = load_tool_declarations(tools_file)
                except Exception as exc:
                    st.error(f"❌ Lỗi tải cấu hình: {exc}")
                    return

                provider = make_provider(provider_name)
                openai_tools = to_openai_tools(tool_declarations)
                artifact_version = build_artifact_version(version, system_prompt, tools_file)
                timestamp = now_iso().replace("-", "").replace(":", "").replace(".", "")
                transcript_id = "_".join([safe_slug(version), safe_slug(provider_name), timestamp])
                transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
                
                transcript: dict[str, Any] = {
                    "transcript_id": transcript_id,
                    **artifact_version_dict(artifact_version),
                    "version": version,
                    "provider": provider_name,
                    "model": selected_model or None,
                    "system_prompt": str(system_prompt),
                    "tools": str(tools_file),
                    "history_window": int(history_window),
                    "max_tool_rounds": int(max_tool_rounds),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "turns": [],
                }
                
                turn_record: dict[str, Any] = {
                    "turn_index": 1,
                    "started_at": now_iso(),
                    "user": user_request,
                    "status": "started",
                    "assistant_text": None,
                    "rounds": [],
                    "tool_events": [],
                }

                messages = [
                    {"role": "system", "content": system_prompt_text},
                    {"role": "user", "content": user_request},
                ]
                
                with st.spinner("⏳ Đang xử lý quá trình Model/Tool loop..."):
                    try:
                        result = run_model_tool_loop(
                            provider=provider,
                            messages=messages,
                            tools=openai_tools,
                            model=selected_model or None,
                            max_tool_rounds=int(max_tool_rounds),
                        )
                        turn_record.update(result)
                        turn_record["ended_at"] = now_iso()
                        transcript["turns"].append(turn_record)
                        write_transcript(transcript_path, transcript)
                        st.success(f"✅ Hoàn thành! Đã lưu log tại `{transcript_path.name}`")
                    except Exception as exc:
                        turn_record.update({
                            "status": "provider_error",
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                        turn_record["ended_at"] = now_iso()
                        transcript["turns"].append(turn_record)
                        write_transcript(transcript_path, transcript)
                        st.error(f"❌ Tiến trình thất bại: {exc}")

                # Hiển thị kết quả bằng Tabs
                st.markdown("### Kết quả thực thi")
                tab_final, tab_trace, tab_meta = st.tabs(["💬 Câu trả lời", "🔄 Vết xử lý (Trace)", "📊 Metadata"])
                
                with tab_final:
                    if transcript["turns"]:
                        turn = transcript["turns"][0]
                        with st.chat_message("user"):
                            st.write(user_request)
                        with st.chat_message("assistant"):
                            st.write(turn.get("assistant_text", "*Không có phản hồi dạng text từ model.*"))
                            
                with tab_trace:
                    if transcript["turns"]:
                        turn = transcript["turns"][0]
                        display_rounds(turn.get("rounds", []))
                        
                with tab_meta:
                    with st.container(border=True):
                        display_transcript_summary(transcript)


if __name__ == "__main__":
    main()
