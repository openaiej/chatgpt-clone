"""
ChatGPT Clone - Streamlit 기반 AI 채팅 앱
OpenAI Agents SDK와 SQLite 세션을 사용해 대화 기록을 유지합니다.
"""

# 환경 변수 로드 (.env 파일의 OPENAI_API_KEY 등)
import dotenv

dotenv.load_dotenv()

import asyncio
import streamlit as st
from agents import Agent, Runner, SQLiteSession, WebSearchTool

# 세션에 에이전트가 없으면 새로 생성 (페이지 새로고침 시 유지)
if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="ChatGPT Clone",
        instructions="""
        You are a helpful assistant.
        
        You have access to the followingn tools:
         - Web Search Tool: Use this when the user asks a questions that isn't in your training data.
           Use this tool when the users asks about current or future events.
           whe you think you don't know the answer. try searching for it in the wer fist.
        """,
        tools=[
            WebSearchTool(),
        ],
    )
agent = st.session_state["agent"]


# 대화 기록을 SQLite DB에 저장하는 세션 (페이지 새로고침 후에도 이력 유지)
if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "chat-gpt-clone-memory.db"
    )
session = st.session_state["session"]


async def paint_history():
    """세션에 저장된 대화 이력을 화면에 그립니다."""
    messages = await session.get_items()

    for message in messages:
        # 사용자/어시스턴트 메시지 렌더링
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.write(message["content"])
                elif message["type"] == "message":
                    st.write(message["content"][0]["text"])

        # 웹 검색 도구 호출 시 표시
        if "type" in message and message["type"] == "web_search_tool_call":
            with st.chat_message("ai"):
                st.write("🔍 Searched the web...")


def update_status(status_container, event):
    """웹 검색 이벤트에 따라 상태 컨테이너 라벨을 업데이트합니다."""
    status_messages = {
        "response.web_search_call.completed": ("✅ Web search completed.", "complete"),
        "response.web_search_call.in_progress": (
            "🔍 Starting web search...",
            "running",
        ),
        "response.web_search_call.searching": (
            "🔍 Web search in progress...",
            "running",
        ),
        "response.completed": (" ", "complete"),
    }
    if event in status_messages:
        label, status = status_messages[event]
        status_container.update(label=label, state=status)


# 앱 로드 시 저장된 대화 이력 표시
asyncio.run(paint_history())

# 채팅 입력창
async def run_agent(message):
    """에이전트에게 메시지를 보내고 스트리밍 응답을 받습니다."""
    with st.chat_message("ai"):
        status_container = st.status("⏳", expanded=False)  # 웹 검색 등 진행 상태 표시
        text_placeholder = st.empty()  # 스트리밍 텍스트 출력용
        response = ""

        stream = Runner.run_streamed(
            agent,
            message,
            session=session,
        )

        async for event in stream.stream_events():
            if event.type == "raw_response_event":
                update_status(status_container, event.event_type)
                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response)


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
