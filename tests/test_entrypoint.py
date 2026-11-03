"""El entrypoint traduce PORT a los argumentos de uvicorn (distroless no tiene shell)."""

import sys

import entrypoint


def _run_entrypoint(monkeypatch, port: str | None) -> list[str]:
    if port is None:
        monkeypatch.delenv("PORT", raising=False)
    else:
        monkeypatch.setenv("PORT", port)
    monkeypatch.setattr(sys, "argv", list(sys.argv))

    captured: dict[str, object] = {}

    def fake_run_module(name: str, run_name: str | None = None) -> None:
        captured["name"] = name
        captured["run_name"] = run_name
        captured["argv"] = list(sys.argv)

    monkeypatch.setattr(entrypoint.runpy, "run_module", fake_run_module)
    entrypoint.main()

    assert captured["name"] == "uvicorn"
    assert captured["run_name"] == "__main__"
    return captured["argv"]


def test_entrypoint_uses_port_from_env(monkeypatch):
    assert _run_entrypoint(monkeypatch, "9000") == [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "9000",
    ]


def test_entrypoint_defaults_to_8000(monkeypatch):
    assert _run_entrypoint(monkeypatch, None)[-1] == "8000"
