---
title: "nook home server"
summary: "Hardware, services, network and backups of the personal home server nook."
tags: [personal, homelab]
---

# nook home server

## Hardware

N100 mini PC, RAM 16GB, NVMe 1TB(시스템, 서비스 데이터), USB 4TB HDD(미디어). Debian 12.

## Services

Caddy(reverse proxy, 자동 TLS), Jellyfin, Vaultwarden, Gitea, Uptime Kuma. 모두 Docker Compose.

## Network

- 외부 노출은 Tailscale로만 한다. 공유기 port forwarding은 없다.
- 내부 도메인은 `*.nook.lan`, Tailscale MagicDNS로 `nook.tail-net.ts.net`.
- Caddy는 Tailscale 인증서(`tailscale cert`)를 쓴다.

## Backup

restic → Backblaze B2. 미디어 HDD는 백업 대상이 아니다.
