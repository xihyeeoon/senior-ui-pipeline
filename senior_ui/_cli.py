r"""모든 명령줄이 맨 앞에서 부르는 것.

`setup_stdout()` 하나뿐이다. 이 파일이 있는 이유는 그 한 줄을 CLI 마다 따로
쓰고 있었기 때문이다 - 네 곳은 쓰고 한 곳은 빠뜨렸고, 빠뜨린 곳이 재구성
루프였다.

그 루프의 `log()` 는 한글과 '—' 를 찍는다. cp949 콘솔에서는 stdout 을 맞추지
않으면 그 글자에서 UnicodeEncodeError 로 죽는다. 죽는 자리가 **요약을 찍는
마지막 단계**라서, 결과 파일은 다 남았는데 종료 코드만 뒤집혔다 - 통과한
실행이 실패로 보인다. 지금까지는 `PYTHONUTF8=1` 을 줘야만 돌았다.

CLI 마다 따로 두지 않는 이유가 그것이다. 빠뜨려도 평소에는 아무 일이 없고,
cp949 콘솔에서 한글을 찍는 순간에만 드러난다.
"""
import sys


def setup_stdout():
    """stdout·stderr 를 UTF-8 로 맞춘다. 무엇이든 찍기 전에 부른다.

    맞추지 못하는 스트림(리디렉션된 파이프의 어떤 래퍼, 테스트의 가짜 stdout)은
    조용히 넘어간다 - 출력 인코딩을 맞추려다 프로그램을 죽이면 본말이 뒤집힌다.

    바꾸지 못했을 때를 위해 errors="replace" 도 함께 건다. 요약을 찍다 죽는
    것보다 글자 하나가 '?' 로 나가는 편이 낫다.
    """
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
