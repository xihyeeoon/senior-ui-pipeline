r"""LLM 재구성-검사 루프. 실행은 `python -m senior_ui.restructure`.

    __main__.py    명령줄 (argparse 하나와 loop.run 호출)
    prompt.py      프롬프트 조립 - 템플릿 · 선택지 요약 · 재시도 블록
    model.py       모델 호출 · 키 읽기 · API 없이 도는 mock
    reply.py       답 가르기 · 흐름 명세 모양 검사
    audit_call.py  senior_ui.audit 을 라이브러리로 부르는 한 지점
    loop.py        재시도 루프 · 예산 · 요약
"""
