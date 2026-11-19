"""Seeded-error measurement of the dream verify judgment (spec 2026-11-19 D3, §7).

Run from the repository root. It runs the logged-in Claude Code (`claude -p`) once:
  uv run --python 3.12 python -m tests.benchmarks.measure_dream_verify [--model MODEL] [--out FILE]

Every case is made up for this file, half in Korean and half in English, so nothing personal is used. Each case
is one memory page with a claim table and one later session exchange on the page's topic:

- A seeded case: what the user typed in the exchange contradicts one claim row of the page.
- A negative control: the user talks about the same topic and nothing on the page stops being true.

The judge answers through the real prompt and adapter, and its answer goes through the same code checks as a dream
run: the per-action field check, the quote in what the user typed, and the claim text in the page.

Reported counts:

- `detected`: seeded cases with a `supersede_claim` naming the seeded row, or a `retire_memory`, that passed the checks.
- `false_alarms`: negative controls with any proposal that passed the checks.
- `dropped_by_checks`: proposals the code checks refused.
- `precision` = detected / (detected + false_alarms), `recall` = detected / seeded cases.

Seeded errors are easier than real drift, so the numbers compare prompt and model versions. They are not the rate
to expect on real sessions.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vault_graph.interface.composition.adapters.claude_dream_judge import ClaudeDreamJudge
from vault_graph.interface.composition.adapters.dream_judge import (
    PROMPT_VERSION,
    VERIFY_ACTIONS,
    DreamItem,
    DreamJudgment,
    DreamPage,
    judgment_problem,
)
from vault_graph.operation.memory.evidence_quote import normalize_evidence_text, quote_in_text
from vault_graph.operation.scope.dream_settings import DREAM_MODEL


@dataclass(frozen=True)
class Case:
    name: str
    title: str
    claims: tuple[str, ...]
    user_text: str
    assistant_text: str
    wrong_claim: str | None
    """The claim row the exchange contradicts. None for a negative control."""


CASES: tuple[Case, ...] = (
    Case(
        "ko-embedding-model",
        "임베딩 모델",
        ("기본 임베딩 모델은 e5-small이다", "임베딩 캐시는 세대 밖에 둔다"),
        "측정 결과 봤어. 기본 임베딩 모델은 이제 arctic-m으로 바꾸자. e5-small은 더 이상 기본이 아니야.",
        "알겠습니다. 기본 프리셋을 arctic-m으로 바꾸겠습니다.",
        "기본 임베딩 모델은 e5-small이다",
    ),
    Case(
        "ko-branch-rule",
        "브랜치 규칙",
        ("기능마다 새 브랜치를 만든다", "커밋 메시지는 한국어로 쓴다"),
        "앞으로는 내가 말하지 않으면 새 브랜치 만들지 마. 지금 기능 브랜치에 그대로 커밋해.",
        "네, 현재 브랜치에 커밋하겠습니다.",
        "기능마다 새 브랜치를 만든다",
    ),
    Case(
        "ko-recall-budget",
        "세션 시작 회상 예산",
        ("세션 시작 회상은 1,500토큰까지 넣는다", "고정 기억을 먼저 넣는다"),
        "회상 예산은 1,500토큰이 너무 커. 1,000토큰으로 줄이기로 하자.",
        "회상 한도를 1,000토큰으로 낮추겠습니다.",
        "세션 시작 회상은 1,500토큰까지 넣는다",
    ),
    Case(
        "ko-release-day",
        "배포 요일",
        ("정기 배포는 매주 금요일에 한다", "배포 전에 전체 테스트를 돌린다"),
        "금요일 배포는 이제 안 해. 정기 배포는 매주 화요일로 옮겼어.",
        "정기 배포 요일을 화요일로 기록하겠습니다.",
        "정기 배포는 매주 금요일에 한다",
    ),
    Case(
        "en-database",
        "Storage engine",
        ("The index is stored in SQLite", "Vectors are stored in Chroma"),
        "We are done with Chroma. From now on vectors live in sqlite-vec, I already removed the Chroma dependency.",
        "Understood, vectors now go to sqlite-vec.",
        "Vectors are stored in Chroma",
    ),
    Case(
        "en-python-version",
        "Python version",
        ("The project supports Python 3.11 and newer", "Tests run with pytest"),
        "Drop 3.11. The minimum supported Python is 3.12 now, I changed pyproject yesterday.",
        "Got it, minimum Python is 3.12.",
        "The project supports Python 3.11 and newer",
    ),
    Case(
        "en-review-cap",
        "Review queue limits",
        ("One cleanup sends at most 10 inferred proposals", "A person accepts every proposal"),
        "Ten is too many for me to review. Make the cap 5 inferred proposals per cleanup from now on.",
        "The cap is now 5 inferred proposals per cleanup.",
        "One cleanup sends at most 10 inferred proposals",
    ),
    Case(
        "en-default-off",
        "Fact extraction default",
        ("Session fact extraction is on by default", "Facts are only a search key"),
        "I changed my mind about the default. Fact extraction should be off by default, people turn it on themselves.",
        "Fact extraction is now off by default.",
        "Session fact extraction is on by default",
    ),
    Case(
        "ko-control-question",
        "임베딩 모델",
        ("기본 임베딩 모델은 e5-small이다", "임베딩 캐시는 세대 밖에 둔다"),
        "기본 임베딩 모델이 뭐였지? e5-small 맞는지 설정 파일에서 확인해 줘.",
        "설정 파일을 확인했습니다. 기본 임베딩 모델은 e5-small입니다.",
        None,
    ),
    Case(
        "ko-control-agree",
        "브랜치 규칙",
        ("기능마다 새 브랜치를 만든다", "커밋 메시지는 한국어로 쓴다"),
        "이번 기능도 평소대로 새 브랜치 만들어서 진행해 줘. 커밋 메시지는 한국어로.",
        "새 브랜치를 만들고 한국어 커밋 메시지로 진행하겠습니다.",
        None,
    ),
    Case(
        "ko-control-one-off",
        "배포 요일",
        ("정기 배포는 매주 금요일에 한다", "배포 전에 전체 테스트를 돌린다"),
        "이번 주만 금요일이 휴일이라 목요일에 배포하자. 다음 주부터는 원래대로야.",
        "이번 주 배포만 목요일로 잡겠습니다.",
        None,
    ),
    Case(
        "ko-control-other-topic",
        "세션 시작 회상 예산",
        ("세션 시작 회상은 1,500토큰까지 넣는다", "고정 기억을 먼저 넣는다"),
        "회상 출력에 오타가 있어. '갱신 필요' 문장의 띄어쓰기를 고쳐 줘.",
        "회상 출력 문장의 띄어쓰기를 고쳤습니다.",
        None,
    ),
    Case(
        "en-control-question",
        "Storage engine",
        ("The index is stored in SQLite", "Vectors are stored in Chroma"),
        "Remind me where the vectors are stored, is it still Chroma? I need to know before I write the backup script.",
        "Yes, vectors are stored in Chroma.",
        None,
    ),
    Case(
        "en-control-agree",
        "Python version",
        ("The project supports Python 3.11 and newer", "Tests run with pytest"),
        "Please run the test suite with pytest on Python 3.11 too, since we still support it.",
        "Ran pytest on Python 3.11 and 3.12, all green.",
        None,
    ),
    Case(
        "en-control-idea",
        "Review queue limits",
        ("One cleanup sends at most 10 inferred proposals", "A person accepts every proposal"),
        "I wonder if 10 proposals is the right number. Do not change anything yet, just tell me how many I resolved.",
        "You resolved 3 proposals last week. Nothing was changed.",
        None,
    ),
    Case(
        "en-control-other-project",
        "Fact extraction default",
        ("Session fact extraction is on by default", "Facts are only a search key"),
        "In my other project the linter is off by default, which annoys me. Anyway, show me the facts status here.",
        "Fact extraction is on with the claude extractor.",
        None,
    ),
)


def page_path(case: Case) -> str:
    return f"wiki/decisions/{case.name}.md"


def page_text(case: Case) -> str:
    rows = "".join(f"| {claim} | stated | raw/sessions/2026-10-01-seed.md L1-L9 |\n" for claim in case.claims)
    return (
        f"---\ntitle: {case.title}\ntype: decision\nstatus: active\nupdated: 2026-10-01\n---\n\n"
        f"# {case.title}\n\n| Claim | Status | Evidence |\n|---|---|---|\n{rows}"
    )


def build_input(cases: Sequence[Case]) -> tuple[list[DreamItem], list[DreamPage]]:
    items = [
        DreamItem(
            key=f"verify:seed:{page_path(case)}:{case.name}",
            date="2026-11-10",
            user_text=case.user_text,
            exchange_text=f"### user\n{case.user_text}\n\n### assistant\n{case.assistant_text}",
            pages=(page_path(case),),
            actions=VERIFY_ACTIONS,
        )
        for case in cases
    ]
    pages = [DreamPage(path=page_path(case), title=case.title, text=page_text(case)) for case in cases]
    return items, pages


def passes_checks(judgment: DreamJudgment, item: DreamItem, case: Case) -> bool:
    """The code checks of a dream run for a verify proposal."""
    if judgment_problem(judgment, item) is not None or not quote_in_text(judgment.quote, case.user_text):
        return False
    if judgment.action == "supersede_claim":
        return normalize_evidence_text(judgment.claim) in normalize_evidence_text(page_text(case))
    return True


def score(cases: Sequence[Case], items: Sequence[DreamItem], judgments: Sequence[DreamJudgment]) -> dict[str, object]:
    by_key = {judgment.key: judgment for judgment in judgments}
    detected: list[str] = []
    missed: list[str] = []
    false_alarms: list[str] = []
    dropped: list[str] = []
    for case, item in zip(cases, items, strict=True):
        judgment = by_key.get(item.key)
        proposed = judgment is not None and judgment.action != "none"
        usable = judgment is not None and proposed and passes_checks(judgment, item, case)
        if proposed and not usable:
            dropped.append(case.name)
        if case.wrong_claim is None:
            if usable:
                false_alarms.append(case.name)
            continue
        hit = (
            judgment is not None
            and usable
            and (
                judgment.action == "retire_memory"
                or normalize_evidence_text(judgment.claim) == normalize_evidence_text(case.wrong_claim)
            )
        )
        (detected if hit else missed).append(case.name)
    seeded = sum(1 for case in cases if case.wrong_claim is not None)
    found = len(detected)
    return {
        "cases": len(cases),
        "seeded": seeded,
        "controls": len(cases) - seeded,
        "detected": found,
        "missed": missed,
        "false_alarms": false_alarms,
        "dropped_by_checks": dropped,
        "precision": round(found / (found + len(false_alarms)), 2) if found + len(false_alarms) else None,
        "recall": round(found / seeded, 2) if seeded else None,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--model", default=DREAM_MODEL)
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args(argv)
    items, pages = build_input(CASES)
    answer = ClaudeDreamJudge(model=arguments.model).judge(items, pages)
    summary = {
        "model": arguments.model,
        "prompt_version": PROMPT_VERSION,
        "cost_usd": answer.cost_usd,
        **score(CASES, items, answer.judgments),
    }
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    if arguments.out is not None:
        arguments.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
