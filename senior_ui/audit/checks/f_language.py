r"""검사 F - 언어. warning.

원본에 없던 영어 단어가 생성물에 나타났는지 본다. 세 곳을 따로 본다.

  runtime    켜진 화면에 렌더된 글 (innerText)
  offscreen  켜진 화면 밖에 떠 있는 것의 글 - 모달·토스트·오버레이. 화면 위에
             덮여 있으므로 사용자는 읽는데, 켜진 화면의 innerText 에는 없다
  attribute  innerText 에 들어오지 않는데 눈에 닿는 글 - placeholder ·
             입력칸의 현재 값 · alt · aria-label · title
  markup     스크립트가 덮어쓰기 전의 마크업. 눈에 닿지 않지만 파일에 남아 있다

속성을 따로 보는 이유는 두 길 다 그것을 놓치기 때문이다. innerText 에는 속성값이
들어오지 않고, 마크업에서 찾는 쪽은 태그를 통째로 걷어내므로 속성값이 함께
사라진다. 그래서 영어 라벨을 전부 placeholder 로 적은 빌드는 경고가 0건이었다.

마크업 쪽은 글이 아닌 것을 먼저 걷어낸다 - script · style · 주석. 세 가지 다
브라우저가 글로 읽지 않으므로 거기 적힌 영어는 "마크업에 들어온 영어" 가 아니다
(markup_words 참고).

어디에 적힌 영어인지를 finding 의 `source` 로 남긴다 - 고칠 곳이 다르다.
원본 파일 어디에든(스크립트 안의 은행·증권사 이름 포함) 있던 단어는 새 영어가
아니다. 한국어가 어색한지, 뜻이 맞는지는 보지 않는다.
"""
import re

ENGLISH = re.compile(r"[A-Za-z][A-Za-z'’]{1,}")


# (source, 그 글을 담은 스냅샷 키, 경고 문구). 순서가 곧 경고의 순서다.
SEEN_SOURCES = [
    ("runtime", "text",
     "English text not present in the original: "),
    ("offscreen", "outside_text",
     "English the original did not have, on something covering the screen "
     "(a modal or overlay outside the lit screen): "),
    ("attribute", "attr_text",
     "English the original did not have, in an attribute the eye still reads "
     "(placeholder / input value / alt / aria-label / title): "),
]


def seen_texts(row):
    """한 화면에서 눈에 닿는 글. source 별로 따로 돌려준다."""
    return [(src, row.get(key) or "") for src, key, _lead in SEEN_SOURCES]


def words(snapshot):
    seen = set()
    for row in snapshot["screens"].values():
        for _src, text in seen_texts(row):
            seen |= set(ENGLISH.findall(text))
    return seen


SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")


def markup_words(html):
    """마크업에 글로 들어 있는 영어 단어.

    글이 아닌 것을 먼저 걷어낸다. script 와 style 의 안쪽은 코드이고, 주석은
    브라우저가 아예 읽지 않는다 - 셋 다 거기 적힌 영어가 화면에 닿지 않는다.

    주석을 따로 걷어내야 하는 이유는 TAG 가 `<` 부터 처음 만나는 `>` 까지만
    지우기 때문이다. 주석 안에 `>` 가 있으면 (`->` 처럼) 주석은 거기서 끊기고
    그 뒤의 글자가 문서의 글로 남는다. 이 저장소의 주석은 한국어 설명에 화살표를
    자주 쓰므로, 걷어내지 않으면 설명에 적힌 영어가 "마크업에 들어온 새 영어" 로
    잡힌다.

    순서는 script/style 이 먼저다. 주석 처리한 마크업(`<!-- <script>… -->`)은
    흔하므로 주석을 먼저 지우면 그 안의 script 가 함께 사라져 결과가 같지만,
    반대로 script 안에 `<!--` 만 있고 `-->` 가 그 바깥에 있으면 주석 지우기가
    `</script>` 를 함께 먹어 script 걷어내기가 어긋난다.

    속성값에 `>` 가 들어 있어도 TAG 가 같은 식으로 끊긴다. 눈에 닿는 속성값은
    이제 `attr_text` 쪽이 따로 보므로 마크업 쪽의 그 한계는 남겨 둔다.
    """
    body = SCRIPT_OR_STYLE.sub(" ", html)
    body = COMMENT.sub(" ", body)
    return set(ENGLISH.findall(TAG.sub(" ", body)))


def run(ctx):
    metrics, W = ctx.metrics, ctx.warn

    new_en = sorted(words(ctx.rep) - words(ctx.orig))
    metrics["new_english_words"] = new_en
    leads = {src: lead for src, _key, lead in SEEN_SOURCES}
    for n in ctx.want:
        row = ctx.rep["screens"].get(n) or {}
        said = set()
        for src, text in seen_texts(row):
            # 같은 단어가 화면 글과 속성에 다 있으면 한 번만 적는다 - 결함은
            # 하나이고, 먼저 오는 source 가 더 눈에 띄는 쪽이다.
            hits = sorted({w for w in new_en if w in text} - said)
            if not hits:
                continue
            said |= set(hits)
            W("F", n, leads[src] + ", ".join(hits), words=hits, source=src)

    # Markup the script overwrites at runtime never reaches the eye, but it is
    # still in the file - password's 재배열 -> "Shuffle" only shows up here.
    #
    # Anything appearing anywhere in the original file - including inside its
    # script, where the 37 bank and 29 securities names live - is not new
    # English. The reassembly merely bakes those into markup.
    static_only = sorted(markup_words(ctx.rep_html)
                         - set(ENGLISH.findall(ctx.orig_html))
                         - words(ctx.orig) - set(new_en))
    metrics["new_english_words_markup_only"] = static_only
    if static_only:
        W("F", None, "English added to the markup but overwritten before it "
          "renders: " + ", ".join(static_only), words=static_only, source="markup")
