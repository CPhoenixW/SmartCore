from __future__ import annotations

import re
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy"

BLOCKED_PUBLIC_PATHS = (
    "/dashboard",
    "/admin",
    "/api",
    "/docs",
    "/backup",
)


def _read(name: str) -> str:
    return (DEPLOY_DIR / name).read_text(encoding="utf-8")


def test_deploy_files_exist() -> None:
    for name in (
        "docker-compose.yml",
        "Caddyfile",
        "Caddyfile.tunnel-boundary",
        "env.example",
        "Dockerfile",
    ):
        assert (DEPLOY_DIR / name).is_file(), f"missing deploy/{name}"


def test_docker_compose_defines_app_and_caddy() -> None:
    compose = _read("docker-compose.yml")
    assert re.search(r"^\s*app:\s*$", compose, re.MULTILINE)
    assert re.search(r"^\s*caddy:\s*$", compose, re.MULTILINE)
    assert "caddy:2" in compose
    assert "deploy/Dockerfile" in compose or "dockerfile: deploy/Dockerfile" in compose


def test_app_port_is_not_published_to_all_interfaces() -> None:
    compose = _read("docker-compose.yml")
    assert '"8000:8000"' not in compose
    assert "- 8000:8000" not in compose
    assert "0.0.0.0:8000" not in compose
    assert "127.0.0.1:8000:8000" in compose or "${APP_BIND:-127.0.0.1}:8000:8000" in compose


def test_docker_compose_defines_tunnel_boundary() -> None:
    compose = _read("docker-compose.yml")
    assert re.search(r"^\s*tunnel-boundary:\s*$", compose, re.MULTILINE)
    assert "caddy:2-alpine" in compose
    assert "Caddyfile.tunnel-boundary" in compose
    assert (
        "172.17.0.1:8000:80" in compose
        or "${TUNNEL_BOUNDARY_BIND:-172.17.0.1}:8000:80" in compose
    )
    assert "depends_on:" in compose
    assert "- app" in compose


def test_tunnel_boundary_caddyfile_only_forwards_feishu_event() -> None:
    caddyfile = _read("Caddyfile.tunnel-boundary")
    assert ":80" in caddyfile
    assert "/feishu/event" in caddyfile
    assert "reverse_proxy app:8000" in caddyfile

    proxied_handles = re.findall(
        r"handle\s+(/[^\s{]+)\s*\{[^}]*reverse_proxy",
        caddyfile,
        flags=re.DOTALL,
    )
    assert proxied_handles == ["/feishu/event"]

    for blocked in BLOCKED_PUBLIC_PATHS:
        assert f"handle {blocked}" not in caddyfile
        assert f"reverse_proxy app:8000{blocked}" not in caddyfile.replace(" ", "")


def test_tunnel_boundary_caddyfile_denies_other_paths() -> None:
    caddyfile = _read("Caddyfile.tunnel-boundary")
    assert re.search(r"handle\s*\{[^}]*respond[^}]*404", caddyfile, re.DOTALL)


def test_caddyfile_only_forwards_feishu_event() -> None:
    caddyfile = _read("Caddyfile")
    assert "/feishu/event" in caddyfile
    assert "reverse_proxy app:8000" in caddyfile

    proxied_handles = re.findall(
        r"handle\s+(/[^\s{]+)\s*\{[^}]*reverse_proxy",
        caddyfile,
        flags=re.DOTALL,
    )
    assert proxied_handles == ["/feishu/event"]

    for blocked in BLOCKED_PUBLIC_PATHS:
        assert f"handle {blocked}" not in caddyfile
        assert f"reverse_proxy app:8000{blocked}" not in caddyfile.replace(" ", "")


def test_caddyfile_denies_other_public_paths() -> None:
    caddyfile = _read("Caddyfile")
    assert re.search(r"handle\s*\{[^}]*respond[^}]*404", caddyfile, re.DOTALL)


def test_env_example_uses_placeholders_only() -> None:
    env_example = _read("env.example")
    assert "your-domain.example.com" in env_example
    assert "your-app-secret" in env_example
    assert "your-verification-token" in env_example
    assert "DATABASE_URL=sqlite:////app/data/smartcore.sqlite" in env_example
    assert "DOMAIN=" in env_example
    assert "APP_BIND=" in env_example
    assert "TUNNEL_BOUNDARY_BIND=" in env_example
    assert "127.0.0.1" in env_example
    assert "172.17.0.1" in env_example


def test_deploy_contract_documents_server_dev_and_openclaw() -> None:
    deploy = Path(__file__).resolve().parents[1].joinpath("deploy.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "prod_repo: /opt/smartcore",
        "dev_repo: /opt/smartcore-dev",
        "OpenClaw",
        "OPENCLAW_EVENTS_ENDPOINT",
        "/agent/db/*",
        "/agent/feedback/*",
        "SmartCore scheduler scans DB every minute",
    ):
        assert phrase in deploy
