from fastapi import FastAPI, Request, Response 
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, List, Optional
import json, os, asyncio, time, re
import sys

sys.path.append("/app")  # ✅ Python이 drift 인식하게 만듦
print("🔥 PYTHONPATH =", sys.path)
print("📂 DIR =", os.listdir("/app"))

# ✅ 에이전트 임포트
from agents.empathy_agent import stream_empathy_reply
from agents.mi_agent import stream_mi_reply
from agents.cbt1_agent import stream_cbt1_reply
from agents.cbt2_agent import stream_cbt2_reply
from agents.cbt3_agent import stream_cbt3_reply

# ✅ 드리프트 감지 로직
from drift.detector import run_detect_and_override

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AgentState(BaseModel):
    stage: Literal["empathy", "mi", "cbt1", "cbt2", "cbt3", "end"]
    question: str
    response: str
    history: List[str]
    turn: Optional[int] = 0
    preset_questions: List[str] = Field(default_factory=list)
    drift_trace: List[bool] = Field(default_factory=list)

model_ready = False
model_paths = {}

@app.on_event("startup")
async def set_model_paths():
    global model_ready, model_paths
    try:
        model_paths = {
            "empathy": "/root/.cache/huggingface/hub/models--youngbongbong--empathymodel/snapshots/8751b89983c92c96a85f2122be99858cf59ffa8f/merged-empathy-8.0B-chat-Q4_K_M.gguf",
            "mi": "/root/.cache/huggingface/hub/models--youngbongbong--mimodel/snapshots/bcc716f72bff0d9a747ad298ade5aecd589e347e/merged-mi-chat-q4_k_m.gguf",
            "cbt1": "/root/.cache/huggingface/hub/models--youngbongbong--cbt1model/snapshots/3616468f47373fafc94181b9eafb7fbe7308fd31/merged-first-8.0B-chat-Q4_K_M.gguf",
            "cbt2": "/root/.cache/huggingface/hub/models--youngbongbong--cbt2model/snapshots/5b068b79f519488cb26703d9837fa5effbe1e316/merged-mid-8.0B-chat-Q4_K_M.gguf",
            "cbt3": "/root/.cache/huggingface/hub/models--youngbongbong--cbt3model/snapshots/05b33fa205d8096df1f3cbe1d9d8ed963b85a0f3/merged-cbt3-8.0B-chat-Q4_K_M.gguf",
        }
        model_ready = True
        print("✅ 모델 경로 등록 완료", flush=True)
    except Exception as e:
        print(f"❌ 모델 경로 등록 실패: {e}", flush=True)
        model_ready = False

@app.get("/")
def root():
    return JSONResponse({"message": "✅ TTM 멀티에이전트 챗봇 서버 실행 중"})

@app.head("/")
def root_head():
    return Response(status_code=200)

@app.get("/status")
def check_model_status():
    return {"ready": model_ready}

@app.post("/chat/stream")
async def chat_stream(request: Request):
    try:
        data = await request.json()
        incoming_state = data.get("state", {})
        incoming_state.setdefault("preset_questions", [])
        incoming_state.setdefault("drift_trace", [])

        state = AgentState(**incoming_state)
        print(f"\n🟢 [입력] STAGE={state.stage.upper()}, TURN={state.turn}, Q='{state.question.strip()}'", flush=True)
    except Exception as e:
        return StreamingResponse(iter([
            r"\n⚠️ 입력 상태를 파싱하는 중 오류가 발생했습니다.\n",
            b"\n---END_STAGE---\n" + json.dumps({
                "next_stage": "empathy",
                "response": "입력 상태가 잘못되었습니다. 다시 시도해 주세요.",
                "turn": 0,
                "history": [],
                "preset_questions": []
            }, ensure_ascii=False).encode("utf-8")
        ]), media_type="text/plain")

    async def async_gen():
        if not model_ready:
            yield r"⚠️ 모델이 아직 준비되지 않았습니다.\n"
            return

        print(f"🧭 [현재 단계] {state.stage.upper()} / 턴: {state.turn}", flush=True)
        print(f"📨 [사용자 질문] '{state.question.strip()}'", flush=True)

        full_text = ""
        start_time = time.time()

        async def collect_stream(generator):
            nonlocal full_text
            async for chunk in generator:
                try:
                    decoded = chunk.decode("utf-8")
                    full_text += decoded
                except Exception as e:
                    print(f"⚠️ [디코딩 오류] {e}", flush=True)
                    continue
                yield chunk

        agent_streams = {
            "empathy": lambda: stream_empathy_reply(state.question.strip(), model_paths["empathy"], state.turn, state),
            "mi": lambda: stream_mi_reply(state, model_paths["mi"]),
            "cbt1": lambda: stream_cbt1_reply(state, model_paths["cbt1"]),
            "cbt2": lambda: stream_cbt2_reply(state, model_paths["cbt2"]),
            "cbt3": lambda: stream_cbt3_reply(state, model_paths["cbt3"]),
        }

        if state.stage not in agent_streams:
            yield r"감사합니다! 모든 세션을 완료하셨습니다. 또 찾아주세요!\n"
            return

        try:
            async for chunk in collect_stream(agent_streams[state.stage]()):
                yield chunk
        except Exception as e:
            print(f"❌ [스트리밍 오류] {e}", flush=True)
            yield f"\n⚠️ 답변 생성 오류: {e}".encode("utf-8")

        elapsed = time.time() - start_time
        print(f"⏱️ [응답 시간] {elapsed:.2f}초", flush=True)

        match = re.search(r'---END_STAGE---\n({.*})', full_text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                state.turn = result.get("turn", 0)
                state.history = result.get("history", [])
                state.response = result.get("response", "")
                state.preset_questions = result.get("preset_questions", [])
            except Exception as e:
                print(f"⚠️ [전이 파싱 실패] {e}", flush=True)

        # ✅ 드리프트 평가 및 전환 여부 반영
        drift_result = run_detect_and_override(state)
        next_stage = "mi" if drift_result == "possible" else result.get("next_stage", state.stage)

        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": next_stage,
            "response": state.response.strip() or "답변 생성 실패",
            "turn": state.turn,
            "history": state.history,
            "preset_questions": state.preset_questions,
            "drift_trace": state.drift_trace
        }, ensure_ascii=False).encode("utf-8")

    return StreamingResponse(async_gen(), media_type="text/plain")

@app.on_event("startup")
async def keep_alive():
    asyncio.create_task(dummy_loop())

async def dummy_loop():
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
