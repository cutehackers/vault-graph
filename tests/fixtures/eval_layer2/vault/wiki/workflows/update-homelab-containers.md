---
title: "Update homelab containers"
summary: "Pull new images on nook one service at a time and roll back if a health check fails."
tags: [personal, homelab]
---

# Update homelab containers

## Steps

1. 업데이트 전에 `restic backup`을 수동으로 한 번 돌린다(`systemctl start restic-backup.service`).
2. 서비스 하나씩 `cd /srv/<service> && docker compose pull && docker compose up -d`.
3. Uptime Kuma에서 초록색이 되는지 5분 본다.
4. 문제가 있으면 `compose.yaml`의 image tag를 이전 버전으로 고정하고 `docker compose up -d`.
5. 모두 끝나면 `docker image prune -f`로 옛 image를 지운다.

## Notes

- Watchtower 자동 업데이트는 쓰지 않는다. Jellyfin 메이저 업데이트가 DB를 바꿔서 한 번 데었다.
- Caddy는 마지막에 업데이트한다. Caddy가 죽으면 다른 서비스 확인도 못 한다.
