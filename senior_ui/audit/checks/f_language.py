r"""검사 F - 언어. warning.

원본에 없던 영어 단어가 생성물에 나타났는지 본다. 세 곳을 따로 본다.

  runtime    화면에 렌더된 글 (innerText)
  attribute  innerText 에 들어오지 않는데 눈에 닿는 글 - placeholder ·
             입력칸의 현재 값 · alt · aria-label · title
  markup     스크립트가 덮어쓰기 전의 마크업. 눈에 닿지 않지만 파일에 남아 있다

속성을 따로 보는 이유는 두 길 다 그것을 놓치기 때문이다. innerText 에는 속성값이
들어오지 않고, 마크업에서 찾는 쪽은 태그를 통째로 걷어내므로 속성값이 함께
사라진다. 그래서 영어 라벨을 전부 placeholder 로 적은 빌드는 경고가 0건이었다.

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


def markup_words(html):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return set(ENGLISH.findall(re.sub(r"<[^>]+>", " ", body)))


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
