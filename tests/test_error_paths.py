r"""오류 경로 - 흐름 명세의 error_paths 와 검사 J.

원본에는 잘못된 입력에서 뜨는 오류가 있다 (계좌번호가 틀림, 은행이 틀림).
검사기가 정답 경로만 걸으면 재설계에서 오류 처리가 통째로 빠져도 잡지 못한다.
여기 있는 테스트는 브라우저 없이 도는 것들이다 - 걷기까지 하는 것은
test_error_paths_browser.py 에 있다.
"""
import _api

F = _api.flow_module


def test_truth_keeps_extra_placeholders():
    """truth 블록의 필수 키 밖의 값(틀린 계좌번호 등)도 자리표시자로 남는다.

    전에는 make_truth 가 필수 키 넷만 골라 담아서, 오류 경로가 쓰는
    {ACCOUNT_WRONG} 이 채워지지 않고 글자 그대로 눌렸다."""
    t = F.make_truth({"BANK": "신한", "ACCOUNT": "1", "AMOUNT": "2", "NAME": "n",
                      "ACCOUNT_WRONG": "9", "BANK_WRONG": "국민"})
    assert t["ACCOUNT_WRONG"] == "9"
    assert t["BANK_WRONG"] == "국민"
    assert F.fill("{ACCOUNT_WRONG}/{ACCOUNT}/{BANK_WRONG}", t) == "9/1/국민"
