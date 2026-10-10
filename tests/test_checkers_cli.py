"""检查器与 CLI 测试."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iterd.checkers import (
    ArtifactRef,
    FilenameConventionChecker,
    MetadataRequiredChecker,
    RuleRef,
    get_checker,
    registered_checkers,
)
from iterd.core.errors import IterdError


def _artifact(filename: str, metadata: dict[str, Any] | None = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=1,
        artifact_code="X",
        artifact_name="X",
        version_id=1,
        version_no=1,
        filename=filename,
        metadata=metadata or {},
    )


def _rule(checker_type: str, params: dict[str, Any], severity: str = "error") -> RuleRef:
    return RuleRef(rule_id=1, code="R", name="R", params=params, severity=severity)


def test_filename_convention() -> None:
    checker = FilenameConventionChecker()
    assert checker.supported_extensions() == ()
    rule = _rule("filename_convention", {"pattern": r"^[A-Z]+_\w+\.dwg$"})
    ok = checker.check(_artifact("BRACKET_revA.dwg"), [rule])
    assert ok == []
    bad = checker.check(_artifact("wrong name.dwg"), [rule])
    assert len(bad) == 1 and bad[0].severity == "error"


def test_metadata_required() -> None:
    checker = MetadataRequiredChecker()
    rule = _rule("metadata_required", {"required": {"材料": "str", "重量": "number"}})
    missing = checker.check(_artifact("a.dwg", {"材料": "Q235"}), [rule])
    assert [f.message for f in missing] == ["缺少必填元数据: 重量"]
    wrong_type = checker.check(_artifact("a.dwg", {"材料": 123, "重量": "heavy"}), [rule])
    assert len(wrong_type) == 1  # 每规则聚合一条发现项
    assert wrong_type[0].location == "metadata"
    assert "类型应为 str" in wrong_type[0].message
    assert checker.check(_artifact("a.dwg", {"材料": "钢", "重量": 1.5}), [rule]) == []


def test_registry() -> None:
    assert set(registered_checkers()) >= {"filename_convention", "metadata_required"}
    assert get_checker("filename_convention") is not None
    with pytest.raises(IterdError) as exc:
        get_checker("nope")
    assert exc.value.code == "ITERD-CHECKER_ERROR"


def test_cli_info(capsys: pytest.CaptureFixture[str]) -> None:
    from iterd.cli import main

    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "iterd" in out


def test_cli_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from iterd.core import config as cfg
    from iterd.core import database as dbmod

    monkeypatch.setenv("ITERD_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/seed.db")
    monkeypatch.setenv("ITERD_DATA_DIR", str(tmp_path / "data"))
    cfg.reset_settings(None)
    dbmod.reset_database()
    from iterd.cli import main

    assert main(["seed"]) == 0
    assert "演示数据注入完成" in capsys.readouterr().out
    # 幂等
    assert main(["seed"]) == 0
    cfg.reset_settings(None)
    dbmod.reset_database()


def test_cli_requires_command() -> None:
    from iterd.cli import _build_parser

    with pytest.raises(SystemExit):
        _build_parser().parse_args([])
