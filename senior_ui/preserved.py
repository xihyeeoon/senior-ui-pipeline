r"""도구가 넣는 데이터 블록의 이름. 넣는 쪽과 보는 쪽이 한 곳에서 읽는다.

도구는 입력 HTML 이 가진 선택지 데이터를 재설계 HTML 에 스크립트 블록 하나로
넣고(`senior_ui/restructure/preserve.py`), 검사 I 는 그 블록을 "값이 있다" 의
증거로 세지 않는다(`senior_ui/audit/checks/i_choices.py`). 두 쪽이 각자 이름을
적으면 한쪽만 바뀌는 날 검사가 조용히 무력해진다 - 블록은 그대로 들어가고 검사는
그것을 빼지 못하므로, 모델이 하나도 그리지 않아도 통과한다. 그래서 이름은 여기
한 곳에만 있다.

`senior_ui` 밑에 두는 이유는 방향이다. 검사기는 재구성 루프를 import 하지 않고
(루프 때문에 바뀌는 모듈이 아니다), 루프도 이 이름 하나 때문에 검사기 안을 뒤질
필요가 없다. 둘 다 이것을 import 한다.
"""
import re

# 블록의 id. 검사 I 가 이 id 로 블록을 찾아 빼고 판정한다.
DATA_BLOCK_ID = "preserved-data"

# 블록이 세우는 전역. 모델은 `window.PRESERVED.<이름>` 으로 읽는다.
GLOBAL_NAME = "PRESERVED"

# id 가 이것인 script 하나. 속성 순서와 따옴표 종류에 매이지 않는다 - 블록을
# 쓰는 쪽은 한 곳이지만, 읽는 쪽이 그 한 가지 모양만 안다면 모양이 바뀌는 날
# 검사가 말없이 블록을 세기 시작한다.
DATA_BLOCK = re.compile(
    r"<script\b[^>]*\bid\s*=\s*[\"']%s[\"'][^>]*>.*?</script>" % DATA_BLOCK_ID,
    re.S | re.I)


def strip_data_block(html):
    """도구가 넣은 데이터 블록을 뺀 HTML. 블록이 없으면 받은 그대로."""
    return DATA_BLOCK.sub("", html or "")
