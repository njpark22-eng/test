"""쓰기 토큰 검사. 토큰 값은 응답·로그에 남기지 않는다."""
import hmac
import os

from fastapi import Header

from vibe_web.errors import ApiError


def write_enabled() -> bool:
    return bool(os.environ.get("WRITE_TOKEN"))


def require_write_token(x_write_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("WRITE_TOKEN", "")
    if not expected:
        raise ApiError(401, "서버에 쓰기 토큰이 설정되지 않아 올릴 수 없습니다. 관리자가 WRITE_TOKEN을 설정해야 합니다")
    if not x_write_token or not hmac.compare_digest(x_write_token.encode("utf-8"), expected.encode("utf-8")):
        raise ApiError(401, "쓰기 토큰이 없거나 맞지 않습니다. 토큰을 확인한 뒤 다시 시도하세요")
