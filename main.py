"""
ChatGPT 클론 - OpenAI Agents SDK 기반 스트리밍 채팅 앱
- 웹 검색, 파일 검색, 이미지 생성, 코드 실행, MCP(Context7) 도구 지원
"""
import dotenv

dotenv.load_dotenv()  # .env에서 OPENAI_API_KEY 로드
from openai import OpenAI
from openai import BadRequestError
import asyncio
import base64
import streamlit as st
from agents import (
    Agent,
    Runner,
    SQLiteSession,
    WebSearchTool,
    FileSearchTool,
    ImageGenerationTool,
    CodeInterpreterTool,
    HostedMCPTool
)

client = OpenAI()

def get_or_create_vector_store():
    """파일 검색용 Vector Store 생성 또는 반환 (업로드된 파일 임베딩 저장)"""
    if "vector_store_id" not in st.session_state:
        vs = client.vector_stores.create(name="chatgpt-clone-files")
        st.session_state["vector_store_id"] = vs.id
    return st.session_state["vector_store_id"]


# ========== 에이전트 초기화 (앱 재시작 시 한 번만 생성) ==========
if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="ChatGPT Clone",
        model="gpt-4o-mini",
        instructions="""
        You are a warm, encouraging Coach. You celebrate the user's achievements and help them with goals and vision. Respond in Korean.

        When the user shares a goal achievement (e.g. "올해 책 10권 읽기 목표 달성했어!"):
            - Congratulate them warmly, then use the Image Generation tool to create a celebration image (e.g. "책 10권 읽기 달성 축하!").
            - Describe the image prompt in a way that fits their achievement.

        When the user asks for a vision board (e.g. "2025년 목표로 비전 보드 만들어 줄 수 있어?"):
            - First use the File Search tool to find their goals/plans document (목표, 계획, 비전 등이 적힌 파일).
            - Summarize what you found (e.g. "목표를 확인했어요: 운동, 한국어 학습, 여행...") and tell the user.
            - Then use the Image Generation tool to create a vision board image that reflects those themes (e.g. 운동, 언어, 여행이 담긴 비전 보드).

        You have access to the following tools:
            - Web Search Tool: Use when the user asks about things outside your training data, current/future events, or when you need to search the web.
            - File Search Tool: Use when the user talks about their own facts, goals, plans, or specific files (e.g. 목표 문서, 계획서). Use this before making vision boards so the image matches their real goals.
            - Image Generation Tool: Use for celebration images and vision boards. Create concrete, positive image prompts.
            - Code Interpreter Tool: Use when you need to write and run code to answer the user's question.
        """,
        tools=[
            WebSearchTool(),  # 실시간 웹 검색
            FileSearchTool(
                vector_store_ids=[get_or_create_vector_store()],
                max_num_results=3,  # 검색 결과 최대 3개
            ),
            ImageGenerationTool(  # 텍스트로 이미지 생성
                tool_config={
                    "type": "image_generation",
                    "quality": "high",
                    "output_format": "jpeg",
                    "partial_images": 1,
                }
            ),
            CodeInterpreterTool(  # Python 코드 작성 및 실행
                tool_config={
                    "type": "code_interpreter",
                    "container": {
                        "type": "auto",
                    },
                }
            ),
            # HostedMCPTool: input[x].action 400 오류 시 일시 비활성화 (SDK/API 호환 이슈)
            # HostedMCPTool(
            #     tool_config={
            #         "server_url": "https://mcp.context7.com/mcp",
            #         "type": "mcp",
            #         "server_label": "Context7",
            #         "server_description": "Use this to get the docs from software projects.",
            #         "require_approval": "never",
            #     }
            # ),
        ],
    )
agent = st.session_state["agent"]

# ========== 대화 기록 세션 (SQLite DB에 저장) ==========
if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "chat-gpt-clone-memory.db",
    )
session = st.session_state["session"]


# ========== 이전 대화 기록을 화면에 표시 ==========
async def paint_history():
    messages = await session.get_items()  # DB에서 대화 내역 조회

    for message in messages:
        if "role" in message:  # 사용자/어시스턴트 메시지
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    content = message["content"]
                    if isinstance(content, str):
                        st.write(content)  # 텍스트 메시지
                    elif isinstance(content, list):
                        for part in content:
                            if "image_url" in part:
                                st.image(part["image_url"])  # 업로드된 이미지

                else:  # 어시스턴트 응답
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"].replace("$", "\\$"))  # LaTeX $ 이스케이프
        if "type" in message:  # 도구 호출 결과 (웹검색, 파일검색 등)
            message_type = message["type"]
            if message_type == "web_search_call":  # 웹 검색 수행됨
                with st.chat_message("ai"):
                    st.write("🔍 Searched the web...")
            elif message_type == "file_search_call":  # 파일 검색 수행됨
                with st.chat_message("ai"):
                    st.write("🗂️ Searched your files...")
            elif message_type == "image_generation_call":  # 이미지 생성 결과
                image = base64.b64decode(message["result"])
                with st.chat_message("ai"):
                    st.image(image)
            elif message_type == "code_interpreter_call":  # 코드 실행 결과
                with st.chat_message("ai"):
                    st.code(message["code"])
            elif message_type == "mcp_list_tools":  # MCP 도구 목록 조회
                with st.chat_message("ai"):
                    st.write(f"Listed {message["server_label"]}'s tools")
            elif message_type == "mcp_call":  # MCP 도구 호출
                with st.chat_message("ai"):
                    st.write(f"Called {message["server_label"]}'s {message["name"]} with args {message["arguments"]}")



asyncio.run(paint_history())  # 앱 로드 시 이전 대화 렌더링


# ========== 도구 실행 상태에 따른 UI 업데이트 ==========
def update_status(status_container, event):

    # 이벤트 타입 → (표시 텍스트, 상태) 매핑
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
        "response.file_search_call.completed": (
            "✅ File search completed.",
            "complete",
        ),
        "response.file_search_call.in_progress": (
            "🗂️ Starting file search...",
            "running",
        ),
        "response.file_search_call.searching": (
            "🗂️ File search in progress...",
            "running",
        ),
        "response.image_generation_call.generating": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.image_generation_call.in_progress": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.image_generation_call.in_progress": (
            "🎨 Drawing image...",
            "running",
        ),
        "response.code_interpreter_call_code.done": (
            "🤖 Ran code.",
            "complete",
        ),
        "response.code_interpreter_call.completed": (
            "🤖 Ran code.",
            "complete",
        ),
        "response.code_interpreter_call.in_progress": (
            "🤖 Running code...",
            "complete",
        ),
        "response.code_interpreter_call.interpreting": (
            "🤖 Running code...",
            "complete",
        ),
        "response.mcp_call.completed": (
            "⚒️ Called MCP tool",
            "complete",
        ),
        "response.mcp_call.failed": (
            "⚒️ Error calling MCP tool",
            "complete",
        ),
        "response.mcp_call.in_progress": (
            "⚒️ Calling MCP tool...",
            "running",
        ),
        "response.mcp_list_tools.completed": (
            "⚒️ Listed MCP tools",
            "complete",
        ),
        "response.mcp_list_tools.failed": (
            "⚒️ Error listing MCP tools",
            "complete",
        ),
        "response.mcp_list_tools.in_progress": (
            "⚒️ Listing MCP tools",
            "running",
        ),
        "response.completed": (" ", "complete"),

    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)


# ========== 사용자 메시지를 받아 에이전트 실행 및 스트리밍 응답 표시 ==========
async def run_agent(message):
    with st.chat_message("ai"):
        status_container = st.status("⏳", expanded=False)  # 도구 실행 상태 표시
        code_placeholder = st.empty()   # 코드 실행 결과 표시 영역
        text_placeholder = st.empty()   # 텍스트 응답 표시 영역
        image_placeholder = st.empty()  # 이미지 생성 결과 표시 영역
        response = ""
        code_response = ""

        # 새 메시지 입력 시 이전 placeholder 비우기 위해 저장
        st.session_state["code_placeholder"] = code_placeholder
        st.session_state["image_placeholder"] = image_placeholder
        st.session_state["text_placeholder"] = text_placeholder

        # 에이전트 실행 (스트리밍 모드로 실시간 응답)
        stream = Runner.run_streamed(
            agent,
            message,
            session=session,
        )

        # 스트리밍 이벤트를 받아 실시간으로 UI 업데이트
        try:
            async for event in stream.stream_events():
                if event.type == "raw_response_event":

                    update_status(status_container, event.data.type)

                    if event.data.type == "response.output_text.delta":  # 텍스트 토큰 수신
                        response += event.data.delta
                        text_placeholder.write(response.replace("$", "\\$"))

                    if event.data.type == "response.code_interpreter_call_code.delta":  # 코드 실행 중
                        code_response += event.data.delta
                        code_placeholder.code(code_response)

                    elif event.data.type == "response.image_generation_call.partial_image":  # 이미지 생성 중
                        image = base64.b64decode(event.data.partial_image_b64)
                        image_placeholder.image(image)
        except BadRequestError:
            raise  # 상위에서 세션 클리어 후 rerun 처리



# ========== 채팅 입력 UI ==========
prompt = st.chat_input(
    "Write a message for your assistant",
    accept_file=True,
    file_type=[
        "txt",
        "jpg",
        "jpeg",
        "png",
    ],
)

# ========== 사용자 입력 처리 ==========
if prompt:
    # 이전 응답 placeholder 비우기
    if "code_placeholder" in st.session_state:
        st.session_state["code_placeholder"].empty()
    if "image_placeholder" in st.session_state:
        st.session_state["image_placeholder"].empty()
    if "text_placeholder" in st.session_state:
        st.session_state["text_placeholder"].empty()

    # 첨부 파일 처리
    for file in prompt.files:
        if file.type.startswith("text/"):  # 텍스트 파일 → Vector Store에 업로드
            with st.chat_message("ai"):
                with st.status("⏳ Uploading file...") as status:
                    uploaded_file = client.files.create(
                        file=(file.name, file.getvalue()),
                        purpose="user_data",
                    )
                    status.update(label="⏳ Attaching file...")
                    client.vector_stores.files.create(
                        vector_store_id=get_or_create_vector_store(),
                        file_id=uploaded_file.id,
                    )
                    status.update(label="✅ File uploaded", state="complete")
        elif file.type.startswith("image/"):  # 이미지 → 세션에 base64로 저장
            with st.status("⏳ Uploading image...") as status:
                file_bytes = file.getvalue()
                base64_data = base64.b64encode(file_bytes).decode("utf-8")
                data_uri = f"data:{file.type};base64,{base64_data}"
                asyncio.run(
                    session.add_items(  # 대화 기록에 이미지 추가
                        [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_image",  # OpenAI API 형식
                                        "detail": "auto",
                                        "image_url": data_uri,
                                    }
                                ],
                            }
                        ]
                    )
                )
                status.update(label="✅ Image uploaded", state="complete")
            with st.chat_message("human"):
                st.image(data_uri)

    if prompt.text:  # 텍스트 메시지가 있으면 에이전트 실행
        with st.chat_message("human"):
            st.write(prompt.text)
        try:
            asyncio.run(run_agent(prompt.text))
        except BadRequestError as e:
            err_msg = str(e)
            if "Unknown parameter" in err_msg:
                asyncio.run(session.clear_session())
                st.error("API 형식 오류로 대화를 비웠어요. 다시 메시지를 보내 주세요. (계속되면 HostedMCPTool 비활성화 상태로 실행 중일 수 있어요)")
                st.rerun()
            else:
                raise


# ========== 사이드바: 메모리 초기화 ==========
with st.sidebar:
    reset = st.button("Reset memory")
    if reset:
        asyncio.run(session.clear_session())
        st.rerun()  # 화면 다시 그리기 → paint_history()가 빈 목록으로 대화창 클리어
    st.write(asyncio.run(session.get_items()))