"""Vercel 진입점. Vercel은 api/ 안의 모든 파일을 함수 경로로 취급하므로(확장자를 뺀 이름이
같으면 충돌) 이 파일만 두고 실제 앱은 vibe_web 패키지에 둔다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vibe_web.main import app  # noqa: E402,F401  (Vercel이 이 모듈의 app을 찾는다)
