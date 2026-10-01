r"""고령 사용자 UI 재구성 파이프라인.

    캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험

패키지로 실행한다. 어느 모듈도 sys.path 를 건드리지 않는다.

    python -m senior_ui.audit              검사기 CLI
    python -m senior_ui.audit.report       검사 결과를 표로
    python -m senior_ui.restructure        재구성-검사 루프
    python -m senior_ui.experiment.server  실험 진행 서버
    python -m senior_ui.experiment.report  세션 집계
    python -m senior_ui.viewer.build_index 뷰어용 색인
    python -m senior_ui.collect_results    증거 파일 복사
"""
