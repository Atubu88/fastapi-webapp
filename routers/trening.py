from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class Numbers(BaseModel):
    num1: float
    num2: float


# 👇 Один endpoint, поддерживающий и POST, и GET
@router.api_route("/calculate", methods=["GET", "POST"])
async def calculate_sum(
        data: Numbers | None = None,
        num1: float | None = Query(None),
        num2: float | None = Query(None)
):
    # Если запрос POST — данные придут в теле (JSON)
    if data:
        result = data.num1 + data.num2
    # Если запрос GET — данные придут как параметры в URL
    elif num1 is not None and num2 is not None:
        result = num1 + num2
    else:
        raise HTTPException(status_code=400, detail="Укажите два числа (num1 и num2).")

    return {"result": result}
