---
title: "Personal commit message conventions"
summary: "Conventional Commits types and scope rules I use across personal projects."
tags: [personal, git, conventions]
---

# Personal commit message conventions

## Rules

- 형식은 `<type>(<scope>): <summary>`. type은 `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`.
- summary는 영어 소문자로 시작하고 마침표를 찍지 않는다. 72자 이하.
- 본문은 한국어로 써도 된다. 왜 바꿨는지를 쓴다.
- breaking change는 `!`를 붙이고 본문에 `BREAKING CHANGE:`를 쓴다.
- gitcrumb 저장소는 crumb 관련 변경에 `crumb:` type을 하나 더 쓴다. git-cliff가 별도 섹션으로 묶는다.

## Why

release-please와 git-cliff 둘 다 이 형식을 읽는다. 프로젝트마다 다르게 쓰면 changelog가 비어 나온다.
