"""API 오류. 본문은 항상 {"error": "한 줄 안내"} 형식이다."""


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra

    def body(self) -> dict:
        return {"error": self.message, **self.extra}
