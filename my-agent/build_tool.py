"""실습 1 — 도구 계약 고정.

설명(description) 두 가지만 변수로 두고 스키마·반환·실패 규칙은 고정한다.
직접 실행하면 문법을 먼저 검사한 뒤 두 계약의 JSON을 출력한다.

    python build_tool.py
"""

import ast
import json

ALLOWED_WAREHOUSES = {"SEOUL-01", "BUSAN-02"}

DESCRIPTIONS = {
    "minimal": "상품 재고를 조회합니다.",
    "contextual": (
        "승인된 창고에서 특정 상품의 현재 가용 재고를 읽기 전용으로 조회합니다. "
        "고객 또는 운영자가 상품 수량을 물을 때만 호출하며, sku에는 상품 SKU를, "
        "warehouse_id에는 SEOUL-01 또는 BUSAN-02만 넣습니다. 수량을 변경하지 않습니다. "
        "성공하면 SKU, 창고, 가용 수량, 확인 시각을 사용합니다. INVALID_SKU이면 SKU를 "
        "확인해 달라고 묻고, WAREHOUSE_NOT_ALLOWED이면 허용된 창고를 요청하며, "
        "TEMPORARY_UNAVAILABLE이면 한 번만 재시도한 뒤 중단합니다."
    ),
}

# --- 1차 실행 관찰 후의 최소 변경 -------------------------------------------
# contextual은 허용값(정의서 ④)만 말하고 '안 쓰는 때'(정의서 ③)를 말하지 않았다.
# 그래서 모델이 창고 미지정에는 SEOUL-01을 지어내고,
# 없는 창고("부산 3번")는 BUSAN-02로 조용히 바꿔치기했다 — 둘 다 오류 없이 통과.
# 바꾸는 것은 설명 문장 두 개뿐. 스키마·반환·실패 규칙·문항은 건드리지 않는다.
DESCRIPTIONS["contextual_v2"] = DESCRIPTIONS["contextual"] + (
    " 창고가 지정되지 않았으면 호출하지 말고 어느 창고인지 되묻습니다. "
    "목록에 없는 창고 이름이면 임의로 가까운 창고로 바꾸지 말고 "
    "허용된 창고 코드를 요청합니다."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sku": {"type": "string", "minLength": 3, "maxLength": 32},
        "warehouse_id": {"type": "string", "enum": sorted(ALLOWED_WAREHOUSES)},
    },
    "required": ["sku", "warehouse_id"],
    "additionalProperties": False,
}


def build_tool(description: str) -> dict:
    return {
        "name": "get_inventory",
        "description": description,
        "input_schema": INPUT_SCHEMA,
        "success_return": {
            "sku": "string",
            "warehouse_id": "string",
            "available_quantity": "integer",
            "checked_at": "ISO-8601 string",
        },
        "failure": {
            "INVALID_SKU": "SKU를 추측하지 말고 확인을 요청합니다.",
            "WAREHOUSE_NOT_ALLOWED": "허용된 창고 코드를 요청합니다.",
            "TEMPORARY_UNAVAILABLE": "한 번만 재시도한 뒤 중단합니다.",
        },
    }


if __name__ == "__main__":
    ast.parse(open(__file__, encoding="utf-8").read())
    for label, description in DESCRIPTIONS.items():
        print(label)
        print(json.dumps(build_tool(description), ensure_ascii=False, indent=2))
