---
title: "Run homelab services with Docker Compose"
summary: "The home server runs services with Docker Compose instead of k3s."
tags: [personal, homelab]
---

# Run homelab services with Docker Compose

## Decision

집 서버(N100 mini PC, 호스트 이름 `nook`)의 서비스는 Docker Compose로 돌린다. k3s는 쓰지 않는다.

## Why

- 서비스가 Jellyfin, Vaultwarden, Gitea, Uptime Kuma, Caddy 다섯 개뿐이다. 노드 하나에서 k3s control plane이 메모리 700MB를 차지했다.
- 장애가 나면 새벽에 혼자 고친다. `docker compose logs`가 kubectl보다 빨리 원인을 보여준다.
- k3s를 배우는 목적은 회사 업무에서 이미 채워진다.

## Layout

서비스마다 `/srv/<service>/compose.yaml`을 두고 Caddy가 reverse proxy를 맡는다.
