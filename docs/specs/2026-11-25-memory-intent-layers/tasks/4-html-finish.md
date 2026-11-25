## id

4

## title

기존 초안 docs/html/2026-11-25-memory-intent-layers.html을 D17/A10에 맞춰 확인하고 마무리한다

## goal

개선 구조를 한국어 다섯 부분으로 오프라인에서 볼 수 있다. 처음부터 쓰지 않고 main session이 쓴 초안(untracked)을 고친다.

## units

D17, A10

## files

- docs/html/2026-11-25-memory-intent-layers.html

## blockers

(none)

## checks

- 수동: 네트워크를 끊고 HTML을 브라우저로 열고, 파일 안에 `http://`, `https://`로 시작하는 `src`나 스타일시트 `href`가 없는지 찾는다 (A10)

## done-when

- [ ] 한국어로 의도1~5, 층 네 개, 쓰기 흐름(수집 → 사실 추출 → 제안·검토 → wiki), 질의 흐름(질의1~6), 코드 연결(앵커, 신선도, 프롬프트 주입) 다섯 부분이 보인다
- [ ] 내용이 spec §2, §4.1~4.3과 어긋나지 않고, 개선 방향마다 decided/proposed가 spec §5와 같게 표시되고 이 spec을 링크한다
- [ ] CSS와 SVG는 파일 안에 있고 외부 자원(`http://`, `https://` src나 stylesheet href)이 없다
