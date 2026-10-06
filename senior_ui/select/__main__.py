r"""C 후보 고르기 - 과제마다 여러 번 돌린 재구성 실행에 순위를 매긴다.

저장된 결과만 읽는다 (summary.json · 마지막 시도의 audit · plan). 모델도
브라우저도 부르지 않는다. 규칙은 flows/selection_rule.json 에 있다.

Usage:
  python -m senior_ui.select --task transfer
  python -m senior_ui.select --task transfer --runs "outputs/restructure_auto/20261007-*"
  python -m senior_ui.select --task transfer --runs results/runs
  python -m senior_ui.select --task transfer --rule my_rule.json
  python -m senior_ui.select --task transfer --rule outputs/selection/transfer_<시각>.json
  python -m senior_ui.select --task transfer --compare outputs/selection/transfer_<시각>.json

--runs 는 실행 폴더나 glob 이다. summary.json 이 없는 폴더를 주면 그 아래의
실행 폴더들을 본다 (results/runs 처럼). 주지 않으면 outputs/restructure_auto/
아래 전부다 - results/runs/ 의 옛 실행은 --runs 로 줄 때만 본다.

--rule 에 지난 고르기의 결과 JSON 을 주면 그때 쓴 규칙을 다시 쓴다.
--compare 는 지난 결과와 지금 결과를 나란히 놓는다 (규칙에서 바뀐 것 · 실행마다
순위가 어떻게 달라졌는지).

결과: outputs/selection/<과제>_<시각>.md 와 같은 내용의 .json.
Exit: 0 = 후보가 있다, 1 = 결과는 썼지만 후보가 없다, 2 = 돌지 못했다.
"""
import argparse
import glob
import io
import json
import os
import sys

from senior_ui._cli import setup_stdout
from senior_ui import config
from senior_ui.tasks import task_names

from .collect import SUMMARY, collect
from .report import build, compare, rel_path, write
from .rule import DEFAULT_RULE, RuleError, load_rule, rank


def default_runs_glob():
    return os.path.join(config.outputs_dir(), "restructure_auto", "*")


def selection_dir():
    return os.path.join(config.outputs_dir(), "selection")


def expand(patterns):
    """--runs 의 폴더 · glob 을 실행 폴더 목록으로. 순서는 이름순, 중복 없음."""
    found = []
    for p in patterns:
        hits = sorted(glob.glob(p)) if glob.has_magic(p) else [p]
        for h in hits:
            if not os.path.isdir(h):
                continue
            inner = [] if os.path.exists(os.path.join(h, SUMMARY)) else \
                [os.path.join(h, c) for c in sorted(os.listdir(h))
                 if os.path.exists(os.path.join(h, c, SUMMARY))]
            # 실행들을 담은 폴더면 그 안의 실행들. 아니면 실행 폴더 하나로 본다 -
            # summary 가 없는 (도중에 죽은) 실행도 순위표에 "없음" 으로 남긴다.
            found += inner or [h]
    seen, out = set(), []
    for f in found:
        key = os.path.normcase(os.path.abspath(f))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return sorted(out, key=lambda f: os.path.basename(os.path.abspath(f)))


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m senior_ui.select")
    ap.add_argument("--task", required=True, choices=task_names(),
                    help="과제 (tasks/<이름>.json). 그 과제의 실행만 본다")
    ap.add_argument("--runs", nargs="+", default=None, metavar="DIR_OR_GLOB",
                    help="볼 실행 폴더나 glob. 주지 않으면 outputs/restructure_auto/*")
    ap.add_argument("--rule", default=None,
                    help="규칙 파일 (기본 flows/selection_rule.json). 지난 고르기의 "
                         "결과 JSON 을 주면 그때의 규칙을 다시 쓴다")
    ap.add_argument("--compare", default=None, metavar="RESULT_JSON",
                    help="지난 고르기 결과와 나란히 놓는다")
    ap.add_argument("--out", default=None,
                    help="결과를 쓸 폴더 (기본 outputs/selection)")
    return ap


def main(argv=None):
    # 무엇이든 찍기 전에 맞춘다 (senior_ui/_cli.py).
    setup_stdout()
    args = build_parser().parse_args(argv)
    try:
        rule, source = load_rule(args.rule or DEFAULT_RULE)
    except RuleError as e:
        print("cannot run: 규칙 - %s" % e, file=sys.stderr)
        return 2
    prev = None
    if args.compare:
        try:
            prev = json.load(io.open(args.compare, encoding="utf-8"))
            prev["rule"]["content"], prev["ranking"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            print("cannot run: --compare %s 를 읽지 못했다: %s" % (args.compare, e),
                  file=sys.stderr)
            return 2
        prev["_path"] = args.compare

    patterns = args.runs or [default_runs_glob()]
    dirs = expand(patterns)
    if not dirs:
        print("cannot run: 실행 폴더가 없다 (%s)" % " ".join(patterns), file=sys.stderr)
        return 2

    rows, other = [], []
    for d in dirs:
        row = collect(d)
        if row.get("task") not in (None, args.task):
            other.append(row["name"])
        else:
            rows.append(row)
    if not rows:
        print("cannot run: %s 과제의 실행이 없다 (본 폴더 %d개, 다른 과제 %d개)"
              % (args.task, len(dirs), len(other)), file=sys.stderr)
        return 2

    ranked = rank(rows, rule)
    result = build(args.task, rule, source, ranked,
                   {"default": args.runs is None, "patterns": [rel_path(p) for p in patterns],
                    "skipped_other_task": other})
    if prev is not None:
        result["compare"] = compare(prev, result)
        prev.pop("_path", None)
    md, js = write(result, args.out or selection_dir(), args.task)

    print("task %s: 실행 %d개 - 후보 %d, 제외 %d (다른 과제 %d개는 넣지 않음)"
          % (args.task, result["counts"]["runs"], result["counts"]["candidates"],
             result["counts"]["excluded"], len(other)))
    for r in ranked["candidates"][:5]:
        print("  %d. %s  warning=%s  대표성=%s  시도=%s"
              % (r["rank"], r["name"], r["warning"],
                 (r.get("representative") or {}).get("distance"), r["attempts"]))
    print("rank1: %s" % (result["rank1"] or "없음"))
    print("md:   %s" % md)
    print("json: %s" % js)
    return 0 if result["rank1"] else 1


if __name__ == "__main__":
    sys.exit(main())
