---
title: "Command Line Interface Guidelines notes"
summary: "Notes from clig.dev that shaped gitcrumb's output and error messages."
tags: [gitcrumb, cli, source]
---

# Command Line Interface Guidelines notes

## Source

Command Line Interface Guidelines(clig.dev).

## Applied to gitcrumb

- 사람용 출력은 stdout, 진단과 log는 stderr.
- stdout이 터미널이 아니면 색을 끈다. `NO_COLOR`도 존중한다.
- 기계용 출력은 `--json` flag로 따로 준다. 사람용 출력 형식은 바꿔도 된다고 문서에 적었다.
- 오류 메시지에는 다음에 할 일을 쓴다(예: "run `gitcrumb doctor`").
- 위험한 동작(notes 전체 삭제)은 `--force` 없이는 확인을 묻는다.
