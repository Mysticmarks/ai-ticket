import time

from ai_ticket.security import TokenManager


def test_token_manager_combines_sources(monkeypatch, tmp_path):
    env_var = "TEST_TOKEN_ENV"
    file_var = "TEST_TOKEN_FILE"
    monkeypatch.setenv(env_var, "env-token")
    token_file = tmp_path / "tokens.txt"
    token_file.write_text("file-token\n")
    monkeypatch.setenv(file_var, str(token_file))

    manager = TokenManager(env_var=env_var, file_env_var=file_var, reload_interval=0.1)

    assert manager.is_valid("env-token")
    assert manager.is_valid("file-token")
    assert not manager.is_valid("missing-token")


def test_token_manager_detects_file_rotations(monkeypatch, tmp_path):
    env_var = "ROTATING_TOKEN_ENV"
    file_var = "ROTATING_TOKEN_FILE"
    monkeypatch.delenv(env_var, raising=False)
    token_file = tmp_path / "tokens.txt"
    token_file.write_text("initial-token\n")
    monkeypatch.setenv(file_var, str(token_file))

    manager = TokenManager(env_var=env_var, file_env_var=file_var, reload_interval=0.1)
    assert manager.is_valid("initial-token")

    token_file.write_text("rotated-token\n")
    time.sleep(0.11)
    assert manager.is_valid("rotated-token")
    assert not manager.is_valid("initial-token")


def test_token_manager_update_tokens(monkeypatch):
    manager = TokenManager(env_var="UNUSED", file_env_var="UNUSED_FILE", reload_interval=1)
    manager.update_tokens({"dynamic-token"})
    assert manager.is_valid("dynamic-token")
