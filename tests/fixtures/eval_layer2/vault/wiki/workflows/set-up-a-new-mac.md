---
title: "Set up a new Mac"
summary: "Bootstrap a new personal or work Mac with Homebrew, chezmoi and mise."
tags: [personal, dotfiles, setup]
---

# Set up a new Mac

## Steps

1. Xcode Command Line Tools: `xcode-select --install`.
2. Homebrew 설치 후 `brew install chezmoi 1password-cli`.
3. `op signin`으로 1Password CLI에 로그인한다. chezmoi template이 비밀값을 여기서 읽는다.
4. `chezmoi init --apply git@github.com:<me>/dotfiles.git`. 회사 기기면 첫 질문에 `work`를 답한다.
5. `brew bundle --file ~/.config/brewfile/Brewfile`로 앱을 설치한다. 회사 기기는 `Brewfile.work`도 함께.
6. `mise install`로 node, go, rust, python 버전을 맞춘다.
7. ssh key는 새로 만들고 GitHub에 등록한다. 옛 기기 key를 복사하지 않는다.

## Notes

- 4번 전에 3번을 하지 않으면 template 렌더링이 실패한다.
