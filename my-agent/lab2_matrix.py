"""실습 1+2 — 설명 2가지 × 문항 3개 = 6회 실행하고 트레이스를 남긴다.

바꾸는 변수: description 하나뿐.
고정: 모델 · temperature · 스키마 · 반환값 · 실패 규칙 · 문항과 그 순서.

실행:
    uv run --with langchain --with langchain-ollama python lab2_matrix.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from build_tool import ALLOWED_WAREHOUSES, DESCRIPTIONS

MODEL = "qwen2.5:3b"
TEMPERATURE = 0
RUN_CMD = "uv run --with langchain --with langchain-ollama python lab2_matrix.py"
OUT = Path("traces")

QUESTIONS = [
    ("q1", "BUSAN-02 창고의 SKU A-17 재고를 알려 줘", "정상 경로"),
    ("q2", "어느 창고든 SKU A-17 재고를 알려 주세요", "창고 미지정"),
    ("q3", "부산 3번 창고의 A-17 재고를 알려 줘", "허용 밖 창고"),
]


def get_inventory_impl(sku: str, warehouse_id: str) -> dict[str, Any]:
    """하네스가 실제로 실행하는 함수. 계약의 반환·실패 규칙을 여기서 집행한다."""
    if warehouse_id not in ALLOWED_WAREHOUSES:
        return {"error": "WAREHOUSE_NOT_ALLOWED",
                "allowed": sorted(ALLOWED_WAREHOUSES)}
    if not (3 <= len(sku) <= 32):
        return {"error": "INVALID_SKU"}
    return {"sku": sku, "warehouse_id": warehouse_id,
            "available_quantity": 7,
            "checked_at": "2026-08-27T01:55:00+09:00"}


def harness_execute(args: dict) -> dict[str, Any]:
    """하네스의 일: 인자를 계약과 대조한 뒤에만 실행한다.

    모델이 필수 인자를 빼고 호출할 수 있으므로, 실행 전에 검사한다.
    이 검사를 건너뛰면 계약 위반이 프로그램 예외로 새어 나간다.
    """
    missing = [k for k in ("sku", "warehouse_id") if not args.get(k)]
    if missing:
        return {"error": "MISSING_REQUIRED_ARG", "missing": missing,
                "allowed_warehouses": sorted(ALLOWED_WAREHOUSES)}
    extra = [k for k in args if k not in ("sku", "warehouse_id")]
    if extra:
        return {"error": "UNKNOWN_ARG", "unknown": extra}
    return get_inventory_impl(args["sku"], args["warehouse_id"])


def make_tool(description: str):
    """설명만 바꿔 같은 계약의 도구를 만든다."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class InventoryArgs(BaseModel):
        sku: str = Field(..., min_length=3, max_length=32)
        warehouse_id: str = Field(..., description="SEOUL-01 또는 BUSAN-02")

    return StructuredTool.from_function(
        func=get_inventory_impl,
        name="get_inventory",
        description=description,
        args_schema=InventoryArgs,
    )


async def run_one(llm, description: str, question: str) -> dict:
    """한 번의 요청·실행·재입력을 돌리고 관찰 항목을 모아 돌려준다."""
    from langchain_core.messages import ToolMessage

    tool = make_tool(description)
    bound = llm.bind_tools([tool])

    rec: dict[str, Any] = {"question": question}
    try:
        r1 = await bound.ainvoke(question)
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec

    rec["prompt_eval_count"] = r1.response_metadata.get("prompt_eval_count")
    rec["tool_calls"] = [(tc["name"], tc["args"]) for tc in r1.tool_calls]

    if not r1.tool_calls:
        rec["tool_result"] = None
        rec["final"] = r1.content
        return rec

    call = r1.tool_calls[0]
    result = harness_execute(call["args"])
    rec["tool_result"] = result

    r2 = await bound.ainvoke(
        [r1, ToolMessage(content=json.dumps(result, ensure_ascii=False),
                         tool_call_id=call["id"])])
    rec["final"] = r2.content
    return rec


def write_trace(path: Path, label: str, qid: str, why: str,
                description: str, rec: dict, stamp: str) -> None:
    lines = [
        f"# trace {label}-{qid}",
        f"모델: {MODEL}    temperature: {TEMPERATURE}",
        f"실행: {RUN_CMD}",
        f"시각: {stamp}",
        f"조건: description = {label}    문항 의도 = {why}",
        "",
        f"[설명 문장]\n{description}",
        "",
        f"[0] 요청 문장\n{rec['question']}",
        "",
    ]
    if "error" in rec:
        lines.append(f"[!] 실행 오류\n{rec['error']}")
    else:
        lines += [
            f"[1] 모델의 요청\n{rec['tool_calls']}",
            f"    prompt_eval_count: {rec['prompt_eval_count']}",
            "",
            f"[2] 하네스의 실행 결과\n"
            + (json.dumps(rec["tool_result"], ensure_ascii=False)
               if rec["tool_result"] is not None else "(도구 호출 없음)"),
            "",
            f"[3] 최종 답\n{rec['final']}",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    from langchain_ollama import ChatOllama

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    llm = ChatOllama(model=MODEL, temperature=TEMPERATURE)

    # 인자로 라벨을 주면 그것만 돌린다 (기존 트레이스를 덮어쓰지 않기 위해).
    wanted = sys.argv[1:] or list(DESCRIPTIONS)
    unknown = [w for w in wanted if w not in DESCRIPTIONS]
    if unknown:
        raise SystemExit(f"모르는 라벨: {unknown}  (가능: {list(DESCRIPTIONS)})")
    print(f"실행할 조건: {wanted}")

    rows = []
    for label in wanted:
        description = DESCRIPTIONS[label]
        for qid, question, why in QUESTIONS:
            rec = await run_one(llm, description, question)
            path = OUT / f"{label}-{qid}.txt"
            write_trace(path, label, qid, why, description, rec, stamp)

            called = rec.get("tool_calls") or []
            args = called[0][1] if called else {}
            rows.append({
                "설명": label,
                "문항": qid,
                "의도": why,
                "호출": "없음" if not called else called[0][0],
                "warehouse_id": args.get("warehouse_id", "-"),
                "sku": args.get("sku", "-"),
                "반환": ("오류:" + rec["tool_result"]["error"])
                        if rec.get("tool_result") and "error" in rec["tool_result"]
                        else ("성공" if rec.get("tool_result") else "-"),
                "토큰": rec.get("prompt_eval_count", "-"),
                "파일": path.name,
            })
            print(f"  done  {label}-{qid}  →  {path}")

    print("\n=== 요약 ===")
    hdr = ["설명", "문항", "의도", "호출", "warehouse_id", "sku", "반환", "토큰"]
    print(" | ".join(f"{h}" for h in hdr))
    for r in rows:
        print(" | ".join(str(r[h]) for h in hdr))

    # 이전 요약을 덮어쓰지 않고 병합한다 (같은 설명·문항이면 새 결과로 교체).
    summary_path = OUT / "summary.json"
    prev = []
    if summary_path.exists():
        prev = json.loads(summary_path.read_text(encoding="utf-8"))
    keys = {(r["설명"], r["문항"]) for r in rows}
    merged = [r for r in prev if (r["설명"], r["문항"]) not in keys] + rows
    summary_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n요약 저장: {summary_path}  (총 {len(merged)}행)")


asyncio.run(main())
