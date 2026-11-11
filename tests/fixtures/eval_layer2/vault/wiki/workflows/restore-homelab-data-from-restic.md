---
title: "Restore homelab data from restic"
summary: "Restore a service's data directory on nook from the restic repository on Backblaze B2."
tags: [personal, homelab, backup]
---

# Restore homelab data from restic

## Steps

1. 해당 서비스를 멈춘다: `cd /srv/<service> && docker compose down`.
2. `source /etc/restic/env`로 B2 key와 저장소 암호를 불러온다.
3. `restic snapshots --tag <service>`로 복원할 snapshot을 고른다.
4. `restic restore <snapshot-id> --target /srv/restore-tmp --include /srv/<service>/data`.
5. 내용을 확인한 뒤 기존 `data`를 `data.broken`으로 옮기고 복원본을 제자리에 둔다.
6. `docker compose up -d` 후 서비스가 뜨는지 Uptime Kuma에서 확인한다.

## Notes

- 백업은 매일 03:30 systemd timer(`restic-backup.timer`)로 돈다. 보관 정책은 daily 7, weekly 4, monthly 6.
- Vaultwarden은 SQLite라서 복원 전에 반드시 컨테이너를 멈춘다.
