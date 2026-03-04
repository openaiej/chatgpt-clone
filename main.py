"""
ChatGPT Clone - Streamlit 기반 AI 채팅 앱
OpenAI Agents SDK와 SQLite 세션을 사용해 대화 기록을 유지합니다.
"""

# 환경 변수 로드 (.env 파일의 OPENAI_API_KEY 등)
import dotenv

dotenv.load_dotenv()

import asyncio
import streamlit as st
from agents import Agent, Runner, SQLiteSession

# 세션에 에이전트가 없으면 새로 생성 (페이지 새로고침 시 유지)
if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="ChatGPT Clone",
        instructions="""
        You are a helpful assistant.
        """
    )
agent = st.session_state["agent"]

# 대화 기록을 SQLite DB에 저장하는 세션 (페이지 새로고침 후에도 이력 유지)
if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "chat-gpt-clone-memory.db"
    )
session = st.session_state["session"]


async def run_agent(message):
    """에이전트에게 메시지를 보내고 스트리밍 응답을 받습니다."""
    result = Runner.run_streamed(
        agent,
        message,
        session=session
    )

    # st.write_stream + async generator는 asyncio.run() 내부에서 이벤트 루프 중첩 에러 발생
    # → placeholder로 수동 스트리밍
    with st.chat_message("ai"):
        placeholder = st.empty()
        full_text = ""
        async for event in result.stream_events():
            if event.type == "raw_response_event" and hasattr(event.data, "delta"):
                full_text += event.data.delta
                placeholder.write(full_text)


# 채팅 입력창
prompt = st.chat_input("Write a message for your assistant")

if prompt:
    # 사용자 메시지 표시
    with st.chat_message("human"):
        st.write(prompt)
    asyncio.run(run_agent(prompt))

# 사이드바: 대화 기록 초기화 및 이력 조회
with st.sidebar:
    reset = st.button("Reset memory")
    if reset:
        asyncio.run(session.clear_session())  # 세션(대화 기록) 초기화
    st.write(asyncio.run(session.get_items()))  # 저장된 대화 이력 표시
