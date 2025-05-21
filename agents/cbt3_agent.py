import os, json, multiprocessing
from typing import AsyncGenerator, Literal, List, Optional
from pydantic import BaseModel
from llama_cpp import Llama

# ✅ 모델 캐시
LLM_CBT3_INSTANCE = {}

def load_cbt3_model(model_path: str) -> Llama:
    global LLM_CBT3_INSTANCE
    if model_path not in LLM_CBT3_INSTANCE:
        print("🚀 CBT3 모델 최초 로딩 중...", flush=True)
        NUM_THREADS = max(1, multiprocessing.cpu_count() - 1)
        LLM_CBT3_INSTANCE[model_path] = Llama(
            model_path=model_path,
            n_threads=NUM_THREADS,
            n_ctx=1500,
            n_batch=8,
            max_tokens=128,
            temperature=0.65,
            top_p=0.9,
            presence_penalty=1.0,
            frequency_penalty=0.8,
            repeat_penalty=1.1,
            n_gpu_layers=0,
            low_vram=True,
            use_mlock=False,
            verbose=False,
            chat_format="llama-3",
            stop=["<|im_end|>"]
        )
        print(f"✅ CBT3 모델 로딩 완료: {model_path}", flush=True)
    return LLM_CBT3_INSTANCE[model_path]

# ✅ 상태 정의
class AgentState(BaseModel):
    stage: Literal["cbt3", "end"]
    question: str
    response: str
    history: List[str]
    turn: int
    intro_shown: bool
    awaiting_preparation_decision: bool = False
    pending_response: Optional[str] = None

# ✅ CBT3 응답 함수
async def stream_cbt3_reply(state: AgentState, model_path: str) -> AsyncGenerator[bytes, None]:
    user_input = state.question.strip()

    # ✅ 처음 진입 시 턴을 0으로 초기화하고 도입 멘트 출력
    if not state.intro_shown:
        intro = (
            "📘 이제 우리는 실천 계획을 세워볼 거예요. 지금까지 정리된 생각을 바탕으로, "
            "앞으로 어떤 행동을 시도해볼 수 있을지 함께 고민해봐요."
        )
        yield intro.encode("utf-8")
        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": "cbt3",
            "turn": 0,
            "response": intro,
            "intro_shown": True,
            "awaiting_preparation_decision": False,
            "history": state.history + [intro]
        }, ensure_ascii=False).encode("utf-8")
        return

    if not user_input:
        fallback = "떠오르는 아이디어나 시도해보고 싶은 변화가 있다면 말씀해 주세요."
        yield fallback.encode("utf-8")
        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": "cbt3",
            "turn": state.turn,
            "response": fallback,
            "intro_shown": state.intro_shown,
            "awaiting_preparation_decision": False,
            "history": state.history
        }, ensure_ascii=False).encode("utf-8")
        return

    try:
        llm = load_cbt3_model(model_path)

        system_prompt = (
            "너는 따뜻하고 논리적인 소크라테스 상담자입니다.\n"
            "- 사용자가 말한 감정, 상황, 목표를 바탕으로 실천 가능한 행동 계획을 세우도록 유도하세요.\n"
            "- 반드시 한 번에 **하나의 질문만** 하세요. 여러 질문을 한 문장에 나열하지 마세요.\n"
            "- 질문은 존댓말로 마무리하며, 단정하지 않고 열린 질문으로 표현하세요.\n"
            "- 실천 전략, 방해 요소 대처, 자기 피드백, 환경 설정, 감정 변화 인식 등 다양한 관점에서 질문하세요.\n"
            "- 같은 구조의 질문 반복은 피하고, 매번 새로운 시각으로 질문을 던지세요.\n"
            "- 예: '그 변화를 위해 가장 먼저 시도해볼 수 있는 행동은 무엇일까요?'"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for i in range(0, len(state.history), 2):
            messages.append({"role": "user", "content": state.history[i]})
            if i + 1 < len(state.history):
                messages.append({"role": "assistant", "content": state.history[i + 1]})
        messages.append({"role": "user", "content": user_input})

        full_response = ""
        first_token_sent = False

        for chunk in llm.create_chat_completion(messages=messages, stream=True):
            token = chunk["choices"][0]["delta"].get("content", "")
            if token:
                full_response += token
                if not first_token_sent:
                    yield b"\n"
                    first_token_sent = True
                yield token.encode("utf-8")

        reply = full_response.strip()

        # ✅ 중복 질문 회피 처리
        last_replies = state.history[-10:]
        if any(reply[:25] in past for past in last_replies if isinstance(past, str)):
            reply += " (이번엔 다른 방식으로 질문드려볼게요.)"

        # ✅ 턴 수 증가 및 종료 조건 확인
        next_turn = state.turn + 1
        is_ending = next_turn >= 5
        next_stage = "end" if is_ending else "cbt3"
        next_turn = 0 if is_ending else next_turn

        if is_ending:
            reply += "\n\n🎯 계획을 잘 세워주셨어요. 이제 대화를 마무리할 시간이에요."

        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": next_stage,
            "turn": next_turn,
            "response": reply,
            "intro_shown": True,
            "awaiting_preparation_decision": False,
            "history": state.history + [user_input, reply]
        }, ensure_ascii=False).encode("utf-8")

    except Exception as e:
        err = f"⚠️ CBT3 응답 오류: {e}"
        print(err, flush=True)
        yield err.encode("utf-8")
        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": "end",
            "turn": 0,
            "response": "⚠️ 예상치 못한 오류가 발생해 대화를 종료합니다.",
            "intro_shown": True,
            "awaiting_preparation_decision": False,
            "history": state.history
        }, ensure_ascii=False).encode("utf-8")
