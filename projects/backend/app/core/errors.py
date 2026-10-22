"""统一错误语义：`{error:{code,message,details}}`（规格 v2 §4.1）。

新域（T2+）API 抛 `ApiError`；参数校验失败统一为 422 VALIDATION_ERROR。
既有内核端点（jobs/health）保持原 HTTPException 行为，待 T11 联调收口。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """业务错误：status_code + 稳定错误码 + 面向用户的消息。"""

    def __init__(self, status_code: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "参数校验失败",
                    "details": exc.errors(),
                }
            },
        )
