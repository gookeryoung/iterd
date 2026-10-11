"""CLI dev/build 前后端联动命令测试."""

from __future__ import annotations

import signal as signal_module
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from iterd import cli


class _FakeProc:
    """subprocess.Popen 替身：记录构造参数，支持 terminate/wait/poll."""

    instances: list[_FakeProc] = []
    wait_results: list[Any] = []

    def __init__(self, cmd: list[str], cwd: str | None = None, **_kwargs: Any) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.pid = 999000 + len(_FakeProc.instances)  # 假 pid：killpg 会因进程组不存在被抑制
        self.terminated = False
        _FakeProc.instances.append(self)

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        result = _FakeProc.wait_results.pop(0) if _FakeProc.wait_results else 0
        if isinstance(result, BaseException):  # KeyboardInterrupt 等基类异常也需抛出
            raise result
        return result


def _patch_popen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.subprocess, "Popen", _FakeProc)


def _noop_signal(*_args: Any) -> None:
    """signal.signal 替身：记录到字典由测试注入."""


def _collect_signal(handlers: dict[Any, Any]) -> Callable[[Any, Any], None]:
    """返回记录注册处理器的 signal.signal 替身."""

    def _fake_signal(sig: Any, handler: Any) -> None:
        handlers[sig] = handler

    return _fake_signal


def _which_none(_cmd: str) -> str | None:
    """shutil.which 替身：始终找不到命令."""
    return None


def _which_ok(cmd: str) -> str | None:
    """shutil.which 替身：仅 pnpm 视为已安装，模拟 CI 无 pnpm 以外的正常环境."""
    return "/usr/bin/pnpm" if cmd == "pnpm" else None


def _run_stub(returncode: int, calls: list[Any] | None = None) -> Callable[..., subprocess.CompletedProcess[str]]:
    """subprocess.run 替身工厂：返回固定退出码，可选记录调用参数."""

    def _run(cmd: list[str], cwd: str | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        if calls is not None:
            calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, returncode)

    return _run


@pytest.fixture(autouse=True)
def _reset_fakes() -> Any:
    _FakeProc.instances = []
    _FakeProc.wait_results = []
    yield


@pytest.fixture()
def fake_frontend(tmp_path: Path) -> Path:
    """构造带 package.json 与 node_modules 的伪前端目录."""
    frontend = tmp_path / "frontend"
    (frontend / "node_modules").mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    return frontend


def test_frontend_dir_in_repo() -> None:
    """源码仓库内应定位到 frontend 目录."""
    frontend = cli._frontend_dir()
    assert frontend is not None
    assert (frontend / "package.json").is_file()


def test_ensure_dev_env_missing_frontend() -> None:
    """frontend 缺失时应退出并提示需在源码仓库运行."""
    with pytest.raises(SystemExit, match="1"):
        cli._ensure_dev_env(None)


def test_ensure_dev_env_missing_pnpm(fake_frontend: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pnpm 未安装时应退出并提示安装."""
    monkeypatch.setattr("shutil.which", _which_none)
    with pytest.raises(SystemExit, match="1"):
        cli._ensure_dev_env(fake_frontend)


def test_build_success(fake_frontend: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """构建成功：调用 pnpm build 且产物 index.html 存在校验通过."""
    monkeypatch.setattr("shutil.which", _which_ok)
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(cli, "_static_dir", lambda: static)
    calls: list[Any] = []
    monkeypatch.setattr(cli.subprocess, "run", _run_stub(0, calls))

    cli.cmd_build()

    assert calls and calls[0][0] == ["pnpm", "build"] and Path(calls[0][1]) == fake_frontend
    assert "[ok] 前端构建完成" in capsys.readouterr().out


def test_build_command_failure(fake_frontend: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pnpm build 返回非零码时应以同码退出."""
    monkeypatch.setattr("shutil.which", _which_ok)
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    monkeypatch.setattr(cli.subprocess, "run", _run_stub(2))
    with pytest.raises(SystemExit, match="2"):
        cli.cmd_build()


def test_build_missing_artifact(fake_frontend: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """构建后产物 index.html 缺失时应以 1 退出."""
    monkeypatch.setattr("shutil.which", _which_ok)
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(cli, "_static_dir", lambda: static)
    monkeypatch.setattr(cli.subprocess, "run", _run_stub(0))
    with pytest.raises(SystemExit, match="1"):
        cli.cmd_build()


def test_dev_starts_both_servers(fake_frontend: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """dev 模式应同时启动 uvicorn --reload 后端与 pnpm dev 前端，并打印访问地址."""
    monkeypatch.setattr("shutil.which", _which_ok)
    _patch_popen(monkeypatch)
    _FakeProc.wait_results = [KeyboardInterrupt()]
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    monkeypatch.setattr(cli.signal, "signal", _noop_signal)

    with pytest.raises(SystemExit):
        cli.cmd_dev("127.0.0.1", None)

    assert len(_FakeProc.instances) == 2
    backend_cmd = _FakeProc.instances[0].cmd
    assert "uvicorn" in backend_cmd and "--reload" in backend_cmd and "8000" in backend_cmd
    assert _FakeProc.instances[1].cmd == ["pnpm", "dev"]
    assert _FakeProc.instances[1].cwd == fake_frontend
    out = capsys.readouterr().out
    assert "http://127.0.0.1:5173" in out and "8000" in out
    # KeyboardInterrupt 清理路径下子进程应被回收
    assert all(p.terminated for p in _FakeProc.instances)


def test_dev_installs_deps_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """node_modules 缺失时应先执行 pnpm install 再启动服务."""
    monkeypatch.setattr("shutil.which", _which_ok)
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    _patch_popen(monkeypatch)
    _FakeProc.wait_results = [KeyboardInterrupt()]
    monkeypatch.setattr(cli, "_frontend_dir", lambda: frontend)
    monkeypatch.setattr(cli.signal, "signal", _noop_signal)
    runs: list[Any] = []
    monkeypatch.setattr(cli.subprocess, "run", _run_stub(0, runs))

    with pytest.raises(SystemExit):
        cli.cmd_dev("127.0.0.1", None)

    assert runs and runs[0][0] == ["pnpm", "install"]


def test_dev_install_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖安装失败时应中止且不启动任何服务."""
    monkeypatch.setattr("shutil.which", _which_ok)
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    _patch_popen(monkeypatch)
    monkeypatch.setattr(cli, "_frontend_dir", lambda: frontend)
    monkeypatch.setattr(cli.subprocess, "run", _run_stub(1))
    with pytest.raises(SystemExit, match="1"):
        cli.cmd_dev("127.0.0.1", None)
    assert _FakeProc.instances == []


def test_dev_port_mismatch_warns(fake_frontend: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """后端端口与 Vite 代理目标（8000）不一致时应输出警告."""
    monkeypatch.setattr("shutil.which", _which_ok)
    _patch_popen(monkeypatch)
    _FakeProc.wait_results = [KeyboardInterrupt()]
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    monkeypatch.setattr(cli.signal, "signal", _noop_signal)

    with pytest.raises(SystemExit):
        cli.cmd_dev("127.0.0.1", 9000)

    assert "[warn]" in capsys.readouterr().err


def test_dev_sigint_handler_cleans_up(fake_frontend: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """注册的 SIGINT 处理器应终止全部子进程并退出；后端正常退出时 dev 静默返回."""
    monkeypatch.setattr("shutil.which", _which_ok)
    _patch_popen(monkeypatch)
    _FakeProc.wait_results = [0]
    monkeypatch.setattr(cli, "_frontend_dir", lambda: fake_frontend)
    handlers: dict[Any, Any] = {}
    monkeypatch.setattr(cli.signal, "signal", _collect_signal(handlers))

    cli.cmd_dev("127.0.0.1", None)  # 后端 wait 返回 0 → 统一回收后正常返回
    assert all(p.terminated for p in _FakeProc.instances)

    handler = handlers[signal_module.SIGINT]
    with pytest.raises(SystemExit, match="0"):
        handler(signal_module.SIGINT, None)


def test_parser_build_and_dev() -> None:
    """参数解析：build 无参数；dev 带 host/port 默认值."""
    args = cli._build_parser().parse_args(["build"])
    assert args.command == "build"
    dev = cli._build_parser().parse_args(["dev"])
    assert dev.command == "dev" and dev.host == "127.0.0.1" and dev.port is None
