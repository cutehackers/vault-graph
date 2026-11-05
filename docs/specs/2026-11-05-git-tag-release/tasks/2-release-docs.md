# Task 2: README, TODO, DECISIONS

## id

2

## title

Point README, TODO and DECISIONS to git-tag releases and record the decision

## goal

After this task, readers of README, TODO and DECISIONS see git tags and GitHub Releases as the only release path. They are told not to use the PyPI package, they see the manual cleanup left for a person, and they can find which past decisions the new entry replaces. This serves Intent 1, and Intent 4 as the documentation for the v0.3.0 release.

## files

- `README.md` (spec §4.5)
- `docs/TODO.md` (spec §4.6, the "Release And Publishing Operations" section only)
- `docs/DECISIONS.md` (spec §4.7, new entry appended at the end)

## blockers

none

## acceptance

A-8, A-9, A-10, and A-11 for this task's files

## checks

- `grep -n 'has releases on PyPI' README.md` (expect no output)
- `grep -nF 'uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git' README.md` (default command still present)
- `grep -nE '@vX\.Y\.Z' README.md` (tag install example present)
- `grep -n 'PUBLISHING.md' README.md` (the More Documentation line has no "PyPI")
- `sed -n '/Release And Publishing Operations/,/^## /p' docs/TODO.md`
- `git diff main -- docs/DECISIONS.md | grep -E '^-[^-]'` (expect no output)
- `tail -n 40 docs/DECISIONS.md`

## done-when

- [ ] README lines 46-49 drop the PyPI sentence. They now say the install command installs `main` from the public GitHub repository over HTTPS, a specific version is installed with `@vX.Y.Z`, and the PyPI package should not be used.
- [ ] The README "Install `vg` only" command is unchanged and has one `@vX.Y.Z` example line added below it.
- [ ] The README More Documentation entry for PUBLISHING.md describes the git tag and GitHub Release process and permissions, without "PyPI".
- [ ] The TODO "Release And Publishing Operations" section states the new direction and has no PyPI upload plan. It lists the person's tasks: decide what to do with the PyPI project, and delete the `pypi`/`testpypi` environments and the Trusted Publishers.
- [ ] DECISIONS ends with `## 2026-11-05 - Release With Git Tags And GitHub Releases Only` in Question/Decision/Reason/Implications form. It names the four replaced entries by date and title: the 2026-06-29 Trusted Publishing entry, the PyPI part of 2026-06-24 onboarding, the PyPI upload part of 2026-10-28, and the publish-workflow reasoning of 2026-11-03. It states that the MIT license decision still stands.
- [ ] No existing DECISIONS line is deleted or changed.
