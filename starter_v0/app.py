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
    trim_history,
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
                    has_error = bool(isinstance(result, dict) and result.get("error"))
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

    turns = transcript.get("turns") or []
    if turns:
        st.markdown("---")
        st.markdown(f"#### Chi tiết các lượt chạy ({len(turns)} turn)")
        st.json([
            {
                "turn_index": turn.get("turn_index"),
                "status": turn.get("status"),
                "started_at": turn.get("started_at"),
                "ended_at": turn.get("ended_at"),
            }
            for turn in turns
        ])


def main() -> None:
    st.set_page_config(page_title="Research Agent UI", page_icon="🤖", layout="wide")

    # ------------------ CONVERSATION SESSION STATE ------------------
    st.session_state.setdefault("transcript", None)
    st.session_state.setdefault("transcript_path", None)
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("turn_index", 0)

    conversation_active = st.session_state.turn_index > 0

    # ------------------ SIDEBAR ------------------
    st.sidebar.title("⚙️ Cấu hình Agent")
    provider_name = st.sidebar.selectbox(
        "Provider", ["openrouter", "openai", "anthropic", "gemini"], index=0, disabled=conversation_active,
    )
    selected_model = st.sidebar.text_input(
        "Model (optional)", placeholder="e.g. gpt-4-turbo", disabled=conversation_active,
    )
    version = st.sidebar.text_input("Artifact version", "v0", disabled=conversation_active)
    
    with st.sidebar.expander("🛠️ Cấu hình nâng cao", expanded=False):
        system_prompt_path = st.text_input(
            "System prompt file", str(ARTIFACTS_DIR / "system_prompt.md"), disabled=conversation_active,
        )
        tools_path = st.text_input(
            "Tools declaration file", str(ARTIFACTS_DIR / "tools.yaml"), disabled=conversation_active,
        )
        max_tool_rounds = st.number_input("Max tool rounds", min_value=1, max_value=10, value=4)
        history_window = st.number_input("History window", min_value=0, max_value=20, value=5)

    st.sidebar.markdown("---")
    if conversation_active:
        st.sidebar.success(f"💬 Hội thoại đang diễn ra — turn {st.session_state.turn_index}")
        st.sidebar.caption(f"Transcript: `{st.session_state.transcript_path.name}`")
        st.sidebar.caption("Cấu hình bị khóa trong lúc hội thoại. Nhấn nút bên dưới để đổi cấu hình.")
    if st.sidebar.button("🆕 Cuộc hội thoại mới", use_container_width=True):
        st.session_state.transcript = None
        st.session_state.transcript_path = None
        st.session_state.history = []
        st.session_state.turn_index = 0
        st.rerun()

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
                        "Status": (t.get("turns") or [{}])[0].get("status"),
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
    st.markdown("Trò chuyện nhiều lượt với Agent — ngữ cảnh hội thoại được giữ xuyên suốt phiên làm việc.")

    # Render the ongoing conversation as a chat feed
    if st.session_state.transcript and st.session_state.transcript["turns"]:
        for turn in st.session_state.transcript["turns"]:
            with st.chat_message("user"):
                st.write(turn.get("user", ""))
            with st.chat_message("assistant"):
                st.write(turn.get("assistant_text") or "*Không có phản hồi dạng text từ model.*")
            with st.container(border=True):
                st.markdown(
                    f"**🔎 Vết xử lý — turn {turn.get('turn_index')} "
                    f"({turn.get('status')})**"
                )
                display_rounds(turn.get("rounds", []))
    else:
        st.info("Chưa có tin nhắn nào. Nhập câu hỏi bên dưới để bắt đầu cuộc hội thoại.")

    system_prompt = Path(system_prompt_path)
    tools_file = Path(tools_path)
    config_ready = system_prompt.exists() and tools_file.exists()
    if not config_ready:
        st.warning("⚠️ Không tìm thấy file System prompt hoặc Tools. Vui lòng kiểm tra lại đường dẫn trước khi chat.")

    user_request = st.chat_input(
        "Nhập câu hỏi hoặc tác vụ nghiên cứu...", disabled=not config_ready,
    )

    if user_request:
        try:
            system_prompt_text = system_prompt.read_text(encoding="utf-8")
            tool_declarations = load_tool_declarations(tools_file)
        except Exception as exc:
            st.error(f"❌ Lỗi tải cấu hình: {exc}")
            return

        provider = make_provider(provider_name)
        openai_tools = to_openai_tools(tool_declarations)

        # First message of the session creates the transcript; later turns append to it.
        if st.session_state.transcript is None:
            artifact_version = build_artifact_version(version, system_prompt, tools_file)
            timestamp = now_iso().replace("-", "").replace(":", "").replace(".", "")
            transcript_id = "_".join([safe_slug(version), safe_slug(provider_name), timestamp])
            st.session_state.transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
            st.session_state.transcript = {
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

        st.session_state.turn_index += 1
        turn_record: dict[str, Any] = {
            "turn_index": st.session_state.turn_index,
            "started_at": now_iso(),
            "user": user_request,
            "status": "started",
            "assistant_text": None,
            "history_window": int(history_window),
            "max_tool_rounds": int(max_tool_rounds),
            "rounds": [],
            "tool_events": [],
        }

        messages = [
            {"role": "system", "content": system_prompt_text},
            *trim_history(st.session_state.history, int(history_window)),
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
                st.session_state.history.append({"role": "user", "content": user_request})
                st.session_state.history.append(
                    {"role": "assistant", "content": result.get("assistant_text") or ""}
                )
            except Exception as exc:
                turn_record.update({
                    "status": "provider_error",
                    "error": f"{type(exc).__name__}: {exc}",
                })
                turn_record["ended_at"] = now_iso()

        st.session_state.transcript["turns"].append(turn_record)
        write_transcript(st.session_state.transcript_path, st.session_state.transcript)
        st.rerun()

    if st.session_state.transcript:
        with st.expander("📊 Metadata transcript hiện tại", expanded=False):
            display_transcript_summary(st.session_state.transcript)


if __name__ == "__main__":
    main()
