import os, json, multiprocessing, difflib
from typing import AsyncGenerator, List
from pydantic import BaseModel
from llama_cpp import Llama

LLM_CBT2_INSTANCE = {}

def load_cbt2_model(model_path: str) -> Llama:
    global LLM_CBT2_INSTANCE
    if model_path not in LLM_CBT2_INSTANCE:
        print("🚀 CBT2 모델 최초 로딩 중...", flush=True)
        NUM_THREADS = max(1, multiprocessing.cpu_count() - 1)
        LLM_CBT2_INSTANCE[model_path] = Llama(
            model_path=model_path,
            n_ctx=1024,
            n_threads=NUM_THREADS,
            n_batch=4,
            max_tokens=128,
            temperature=0.6,
            top_p=0.85,
            repeat_penalty=1.1,
            n_gpu_layers=0,
            low_vram=True,
            use_mlock=False,
            verbose=False,
            chat_format="llama-3",
            stop=["<|im_end|>", "\n\n"]
        )
        print("✅ CBT2 모델 로드 완료", flush=True)
    return LLM_CBT2_INSTANCE[model_path]

class AgentState(BaseModel):
    question: str
    response: str
    history: List[str]
    turn: int
    intro_shown: bool

def get_cbt2_prompt() -> str:
    return (
        "너는 인지 재구조화를 도와주는 전문 CBT 상담자야.\n"
        "- 반드시 한 번에 하나의 질문만 하세요. 여러 질문을 나열하지 마세요.\n"
        "- 자동사고에 도전하고 왜곡된 사고를 재구성할 수 있도록 다양한 관점의 질문을 해.\n"
        "- 주제를 돌아가며 질문해: 감정, 사실 여부, 대안 해석, 가치 판단, 신념 검토, 타인의 관점, 장기적 영향, 반복된 패턴, 긍정적 가능성 등\n"
        "- 질문은 존댓말로 짧고 따뜻하게 마무리해 주세요.\n"
        "- 같은 구조의 질문은 반복하지 마세요.\n"
        "- 예시:\n"
        "  - '그 생각은 어떤 근거에서 비롯된 걸까요?'\n"
        "  - '혹시 이전에도 비슷한 상황을 경험하신 적 있으신가요?'\n"
        "  - '그 생각이 지속된다면 어떤 장기적인 영향이 생길 수 있을까요?'\n"
        "  - '다른 시각에서 보면 이 상황을 어떻게 볼 수 있을까요?'\n"
        "  - '이 생각이 지금의 감정에 어떤 영향을 주고 있을까요?'"
    )

async def stream_cbt2_reply(state: AgentState, model_path: str) -> AsyncGenerator[bytes, None]:
    user_input = state.question.strip()
    if not user_input:
        fallback = "조금 더 구체적으로 말씀해주실 수 있을까요?"
        yield fallback.encode("utf-8")
        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": "cbt2",
            "response": fallback,
            "history": state.history + [user_input, fallback],
            "turn": state.turn + 1,
            "intro_shown": True
        }, ensure_ascii=False).encode("utf-8")
        return

    try:
        llm = load_cbt2_model(model_path)
        messages = [{"role": "system", "content": get_cbt2_prompt()}]
        for i in range(max(0, len(state.history) - 10), len(state.history), 2):
            messages.append({"role": "user", "content": state.history[i]})
            if i + 1 < len(state.history):
                messages.append({"role": "assistant", "content": state.history[i + 1]})
        messages.append({"role": "user", "content": user_input})

        full_response, first_token_sent = "", False
        for chunk in llm.create_chat_completion(messages=messages, stream=True):
            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if token:
                full_response += token
                if not first_token_sent:
                    yield b"\n"
                    first_token_sent = True
                yield token.encode("utf-8")

        # ✅ 리스트로 나오는 경우 문자열로 정리
        if isinstance(full_response, list):
            reply = " ".join(str(x) for x in full_response)
        else:
            reply = str(full_response).strip()

        # ✅ 유사 질문 회피: 최근 5개 assistant 응답과 비교
        for past in state.history[-10:]:
            if isinstance(past, str):
                similarity = difflib.SequenceMatcher(None, reply[:30], past[:30]).ratio()
                if similarity > 0.85:
                    reply += " (이번에는 다른 방향으로 생각해볼 수 있도록 질문드려볼게요.)"
                    break

        # ✅ 5턴 이상이면 CBT3로 전환
        next_stage = "cbt3" if state.turn + 1 >= 5 else "cbt2"

        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": next_stage,
            "response": reply,
            "history": state.history + [user_input, reply],
            "turn": state.turn + 1,
            "intro_shown": True
        }, ensure_ascii=False).encode("utf-8")

    except Exception as e:
        print(f"⚠️ CBT2 오류: {e}", flush=True)
        fallback = "죄송합니다. 다시 말씀해 주실 수 있을까요?"
        yield fallback.encode("utf-8")
        yield b"\n---END_STAGE---\n" + json.dumps({
            "next_stage": "cbt2",
            "response": fallback,
            "history": state.history + [user_input],
            "turn": state.turn + 1,
            "intro_shown": True
        }, ensure_ascii=False).encode("utf-8")

