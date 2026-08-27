"""실습 2 (1부) — 요청과 실행을 분리해 관찰한다.

강의 코드에서 모델만 교체했다.
  강의: qwen3.5:2b  →  여기: qwen2.5:3b
  이유: qwen3.5는 미설치. qwen2.5는 2b가 없고, 3b가 형식 안정 최소로 실측된 값.
       2b급을 쓰면 도구 호출 형식이 조건과 무관하게 깨져 실습 목적이 무너진다.
  qwen2.5는 thinking 미지원(Capabilities: completion, tools)이라 reasoning 인자를 넣지 않는다.

실행:
    uv run --with langchain --with langchain-ollama python lab2_toolcall.py
"""

import asyncio
import json
from typing import Any

MODEL = "qwen2.5:3b"
QUESTION = "BUSAN-02 창고의 SKU A-17 재고를 알려 줘"


async def main():
    from langchain_core.tools import tool
    from langchain_core.messages import ToolMessage
    from langchain_ollama import ChatOllama

    @tool
    def get_inventory(sku: str, warehouse_id: str) -> dict[str, Any]:
        """승인된 창고에서 특정 상품의 현재 가용 재고를 읽기 전용으로 조회합니다.
        sku에는 상품 SKU를, warehouse_id에는 SEOUL-01 또는 BUSAN-02만 넣습니다.
        수량을 변경하지 않습니다. INVALID_SKU이면 SKU를 확인해 달라고 물어야 합니다."""
        if warehouse_id not in ("SEOUL-01", "BUSAN-02"):
            return {"error": "WAREHOUSE_NOT_ALLOWED"}
        return {"sku": sku, "warehouse_id": warehouse_id,
                "available_quantity": 7, "checked_at": "2026-08-27T01:55:00+09:00"}

    llm = ChatOllama(model=MODEL, temperature=0)
    llm_with_tools = llm.bind_tools([get_inventory])

    r1 = await llm_with_tools.ainvoke(QUESTION)
    print("[1] 모델의 요청:", [(tc["name"], tc["args"]) for tc in r1.tool_calls])
    print("    prompt_eval_count:", r1.response_metadata.get("prompt_eval_count"))

    if not r1.tool_calls:
        print("    !! 도구 호출이 없음. 최종 텍스트:", r1.content[:200])
        return

    result = get_inventory.invoke(r1.tool_calls[0]["args"])
    print("[2] 하네스의 실행 결과:", json.dumps(result, ensure_ascii=False))

    r2 = await llm_with_tools.ainvoke(
        [r1, ToolMessage(content=json.dumps(result, ensure_ascii=False),
                         tool_call_id=r1.tool_calls[0]["id"])])
    print("[3] 결과를 읽은 최종 답:", r2.content[:200])


asyncio.run(main())
