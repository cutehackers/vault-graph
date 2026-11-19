"""Seeded-error measurement of the dream verify judgment (spec 2026-11-19 D3, §7).

Run from the repository root. It runs the logged-in Claude Code (`claude -p`) once:
  uv run --python 3.12 python -m tests.benchmarks.measure_dream_verify [--model MODEL] [--out FILE]

Every case is made up for this file, half in Korean and half in English, so nothing personal is used. Each case
is one memory page and one later session exchange on the page's topic:

- A seeded case: what the user typed in the exchange contradicts the page.
- A negative control: the user talks about the same topic and nothing on the page stops being true (a question,
  agreement, a one-time exception, another matter, an idea that is not a decision, another project).

Sixteen pages have a claim table with two rows, of which a seeded case contradicts one. Four pages have the
shape `remember` writes and hold one fact.

The judge sees nothing that tells the two kinds apart: page paths and item keys are numbers in judging order.
Cases go to the judge in batches of ``BATCH_SIZE``, as in a dream run, in a fixed order that mixes seeded cases
and controls in every batch and never puts two cases with the same page text in one batch. Each answer goes
through the same code checks as a dream run: the per-action field check, the quote in what the user typed, the
claim text in the page, and the page shape for an update.

A seeded case counts as detected only when the proposal is the right correction:

- claim-table page: `supersede_claim` naming the seeded row. `retire_memory` is wrong there, because the other
  row is still true, and is counted under `retired_whole_page`.
- one-fact page: `update_memory` or `retire_memory`.

Reported counts: `detected`, `missed`, `false_alarms` (controls with any proposal that passed the checks),
`dropped_by_checks` (proposals the code refused), `retired_whole_page`, `precision` = detected / (detected +
false_alarms) and `recall` = detected / seeded cases.

Seeded errors are easier than real drift, and the sample is small, so the numbers only compare prompt and model
versions. They are not the rate to expect on real sessions.
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
from vault_graph.interface.composition.adapters.dream_worker import BATCH_SIZE, memory_page_parts
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
    """The claim the exchange contradicts. None for a negative control."""
    claim_table: bool = True
    """False for a page in the shape `remember` writes: a heading, a body and an evidence section."""


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
    Case(
        "ko-note-seeded",
        "코드 리뷰 방식",
        ("코드 리뷰는 PR마다 사람 한 명이 승인해야 머지한다",),
        "리뷰 규칙 바꿨어. 이제 사람 승인은 필요 없고 CI가 통과하면 바로 머지해도 돼.",
        "알겠습니다. CI 통과만 확인하고 머지하겠습니다.",
        "코드 리뷰는 PR마다 사람 한 명이 승인해야 머지한다",
        claim_table=False,
    ),
    Case(
        "en-note-seeded",
        "Log format",
        ("Logs are written as plain text lines",),
        "We switched the log format last week. Logs are JSON lines now, not plain text. Keep that in mind.",
        "Noted, logs are JSON lines.",
        "Logs are written as plain text lines",
        claim_table=False,
    ),
    Case(
        "ko-note-control",
        "테스트 실행 방법",
        ("테스트는 uv run pytest로 실행한다",),
        "테스트 돌릴 때 평소처럼 uv run pytest 쓰면 되지? 한 번 돌려 줘.",
        "uv run pytest로 실행했고 모두 통과했습니다.",
        None,
        claim_table=False,
    ),
    Case(
        "en-note-control",
        "Commit message language",
        ("Commit messages are written in Korean",),
        "Write this one commit message in English because the upstream project asked for it. Only this commit.",
        "Wrote this commit message in English.",
        None,
        claim_table=False,
    ),
)

# Judging order. Every batch of BATCH_SIZE mixes seeded cases and controls, and no batch holds two cases that
# share a page text (case n and its control share one: 0/8, 1/9, 2/11, 3/10, 4/12, 5/13, 6/14, 7/15).
ORDER: tuple[int, ...] = (0, 10, 4, 14, 1, 11, 5, 15, 8, 2, 12, 6, 9, 3, 13, 7, 16, 18, 17, 19)


def ordered_cases() -> tuple[Case, ...]:
    return tuple(CASES[index] for index in ORDER)


def page_path(position: int) -> str:
    """A path that names only the judging position, so it tells the judge nothing about the case."""
    return f"wiki/decisions/d-{position + 1:02d}.md"


def page_text(case: Case) -> str:
    front = f"---\ntitle: {case.title}\ntype: decision\nstatus: active\nupdated: 2026-10-01\n---\n\n# {case.title}\n\n"
    if not case.claim_table:
        evidence = "- Evidence: raw/sessions/2026-10-01-seed.md L1-L9\n"
        return f"{front}{case.claims[0]}.\n\n## Evidence\n\nStatus: stated\n\n{evidence}"
    rows = "".join(f"| {claim} | stated | raw/sessions/2026-10-01-seed.md L1-L9 |\n" for claim in case.claims)
    return f"{front}| Claim | Status | Evidence |\n|---|---|---|\n{rows}"


def build_input(cases: Sequence[Case]) -> tuple[list[DreamItem], list[DreamPage]]:
    """One verify item and its page per case, in the order given."""
    items = [
        DreamItem(
            key=f"verify:seed:{page_path(position)}:x{position + 1:02d}",
            date="2026-11-10",
            user_text=case.user_text,
            exchange_text=f"### user\n{case.user_text}\n\n### assistant\n{case.assistant_text}",
            pages=(page_path(position),),
            actions=VERIFY_ACTIONS,
        )
        for position, case in enumerate(cases)
    ]
    pages = [
        DreamPage(path=page_path(position), title=case.title, text=page_text(case))
        for position, case in enumerate(cases)
    ]
    return items, pages


def passes_checks(judgment: DreamJudgment, item: DreamItem, case: Case) -> bool:
    """The code checks of a dream run for a verify proposal."""
    if judgment_problem(judgment, item) is not None or not quote_in_text(judgment.quote, case.user_text):
        return False
    if judgment.action == "supersede_claim":
        return normalize_evidence_text(judgment.claim) in normalize_evidence_text(page_text(case))
    if judgment.action == "update_memory":
        return memory_page_parts(page_text(case)) is not None
    return True


def _is_right_correction(judgment: DreamJudgment, case: Case) -> bool:
    if case.claim_table:
        return judgment.action == "supersede_claim" and normalize_evidence_text(
            judgment.claim
        ) == normalize_evidence_text(case.wrong_claim or "")
    return judgment.action in ("update_memory", "retire_memory")


def score(cases: Sequence[Case], items: Sequence[DreamItem], judgments: Sequence[DreamJudgment]) -> dict[str, object]:
    by_key = {judgment.key: judgment for judgment in judgments}
    detected: list[str] = []
    missed: list[str] = []
    false_alarms: list[str] = []
    dropped: list[str] = []
    retired_whole_page: list[str] = []
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
        if judgment is not None and usable and case.claim_table and judgment.action == "retire_memory":
            retired_whole_page.append(case.name)
        hit = judgment is not None and usable and _is_right_correction(judgment, case)
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
        "retired_whole_page": retired_whole_page,
        "precision": round(found / (found + len(false_alarms)), 2) if found + len(false_alarms) else None,
        "recall": round(found / seeded, 2) if seeded else None,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--model", default=DREAM_MODEL)
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args(argv)
    cases = ordered_cases()
    items, pages = build_input(cases)
    judge = ClaudeDreamJudge(model=arguments.model)
    judgments: list[DreamJudgment] = []
    cost = 0.0
    batches = 0
    for start in range(0, len(items), BATCH_SIZE):
        answer = judge.judge(items[start : start + BATCH_SIZE], pages[start : start + BATCH_SIZE])
        judgments.extend(answer.judgments)
        cost += answer.cost_usd or 0.0
        batches += 1
    summary = {
        "model": arguments.model,
        "prompt_version": PROMPT_VERSION,
        "batches": batches,
        "cost_usd": round(cost, 4),
        "actions": {
            action: sum(1 for judgment in judgments if judgment.action == action)
            for action in sorted({judgment.action for judgment in judgments})
        },
        **score(cases, items, judgments),
    }
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    if arguments.out is not None:
        arguments.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
