import uuid

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, message: str, category: str = "VALIDATION_ERROR", errors: list | None = None, context: dict | None = None, sub_category: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.category = category
        self.errors = errors or []
        self.context = context
        self.sub_category = sub_category

    def body(self) -> dict:
        b = {"status": "error", "message": self.message, "correlationId": str(uuid.uuid4()), "category": self.category}
        if self.sub_category:
            b["subCategory"] = self.sub_category
        if self.errors:
            b["errors"] = self.errors
        if self.context:
            b["context"] = self.context
        return b


def not_found(message: str = "resource not found") -> ApiError:
    return ApiError(404, message, "OBJECT_NOT_FOUND")


def validation(message: str, errors: list | None = None) -> ApiError:
    return ApiError(400, message, "VALIDATION_ERROR", errors)


def conflict(message: str) -> ApiError:
    return ApiError(409, message, "CONFLICT")


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.body())
