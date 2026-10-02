r"""검사 F - 언어. warning.

원본에 없던 영어 단어가 생성물에 나타났는지 본다. 화면에 실제로 렌더된 글과,
스크립트가 덮어쓰기 전의 마크업을 따로 본다 - 후자는 눈에 닿지 않지만 파일에
남아 있다. 원본 파일 어디에든(스크립트 안의 은행·증권사 이름 포함) 있던 단어는
새 영어가 아니다. 한국어가 어색한지, 뜻이 맞는지는 보지 않는다.
"""
import re

ENGLISH = re.compile(r"[A-Za-z][A-Za-z'’]{1,}")


def words(snapshot):
    seen = set()
    for row in snapshot["screens"].values():
        seen |= set(ENGLISH.findall(row.get("text") or ""))
    return seen


def markup_words(html):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return set(ENGLISH.findall(re.sub(r"<[^>]+>", " ", body)))


def run(ctx):
    metrics, W = ctx.metrics, ctx.warn

    new_en = sorted(words(ctx.rep) - words(ctx.orig))
    metrics["new_english_words"] = new_en
    for n in ctx.want:
        t = (ctx.rep["screens"].get(n) or {}).get("text") or ""
        hits = sorted({w for w in new_en if w in t})
        if hits:
            W("F", n, "English text not present in the original: "
              + ", ".join(hits), words=hits, source="runtime")

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
