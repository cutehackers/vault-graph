---
title: "Rust error handling notes"
summary: "When gitcrumb uses thiserror versus anyhow, and how errors map to exit codes."
tags: [personal, rust, study, gitcrumb]
---

# Rust error handling notes

## Rule of thumb

- library crate(`gitcrumb-core`)는 `thiserror`로 구체적인 error enum을 만든다. 호출자가 match할 수 있어야 한다.
- binary crate(`gitcrumb-cli`)는 `anyhow::Result`로 받아서 context를 붙인다(`.with_context(|| ...)`).
- `main`에서 error 종류를 보고 exit code를 정한다: `CoreError::Git` → 2, 사용자 입력 오류 → 1, 나머지 → 3.

## Pitfall

`anyhow`로 감싼 뒤에는 `downcast_ref::<CoreError>()`로만 원래 종류를 꺼낼 수 있다. context를 여러 겹 붙여도 downcast는 된다.
