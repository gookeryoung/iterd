"""检查器与 CLI 测试."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iterd.checkers import (
    ArtifactCodeConventionChecker,
    ArtifactRef,
    CheckContext,
    FileExtensionWhitelistChecker,
    FilenameConventionChecker,
    Finding,
    MetadataRangeChecker,
    MetadataRequiredChecker,
    RuleRef,
    checker_manifest,
    get_checker,
    get_context_checker,
    register_context_checker,
    registered_checkers,
    registered_context_checkers,
)
from iterd.core.errors import IterdError


def _artifact(filename: str, metadata: dict[str, Any] | None = None, code: str = "X") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=1,
        artifact_code=code,
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


def test_artifact_code_convention() -> None:
    checker = ArtifactCodeConventionChecker()
    assert checker.supported_extensions() == ()
    rule = _rule("artifact_code_convention", {"pattern": r"^[A-Z]{3}-\d{3,}$"})
    assert checker.check(_artifact("a.dxf", code="SHF-301"), [rule]) == []
    bad = checker.check(_artifact("a.dxf", code="shf-301"), [rule])
    assert len(bad) == 1 and bad[0].severity == "error"
    assert bad[0].location == "shf-301"
    assert "产物编码 shf-301 不符合规范" in bad[0].message
    # 空 pattern 放行（缺配置即跳过）
    assert checker.check(_artifact("a.dxf", code="x"), [_rule("artifact_code_convention", {})]) == []


def test_metadata_range() -> None:
    checker = MetadataRangeChecker()
    rule = _rule("metadata_range", {"ranges": {"重量kg": {"min": 0.1, "max": 500}}})
    # 范围内（含恰好等于上下限边界值）通过
    assert checker.check(_artifact("a.csv", {"重量kg": 500}), [rule]) == []
    assert checker.check(_artifact("a.csv", {"重量kg": 0.1}), [rule]) == []
    over = checker.check(_artifact("a.csv", {"重量kg": 3200}), [rule])
    assert len(over) == 1 and over[0].location == "metadata"
    assert "元数据 重量kg 超出上限 500" in over[0].message
    under = checker.check(_artifact("a.csv", {"重量kg": 0.05}), [rule])
    assert "元数据 重量kg 低于下限 0.1" in under[0].message
    # 非数值（字符串与 bool 均算类型问题，bool 不参与范围比较）
    assert "元数据 重量kg 应为数值" in checker.check(_artifact("a.csv", {"重量kg": "约4.2"}), [rule])[0].message
    assert "元数据 重量kg 应为数值" in checker.check(_artifact("a.csv", {"重量kg": True}), [rule])[0].message
    # 缺失键不报（必填职责归 metadata_required）
    assert checker.check(_artifact("a.csv"), [rule]) == []
    # 多键问题聚合一条发现项
    two = checker.check(
        _artifact("a.csv", {"重量kg": 3200, "壁厚mm": "薄"}),
        [_rule("metadata_range", {"ranges": {"重量kg": {"max": 500}, "壁厚mm": {"min": 1}}})],
    )
    assert len(two) == 1 and "; " in two[0].message
    # 非法边界配置（非 dict 规格 / 非数值边界 / bool 边界）视为该侧不约束
    lax = _rule("metadata_range", {"ranges": {"重量kg": 5, "壁厚mm": {"min": True, "max": "厚"}}})
    assert checker.check(_artifact("a.csv", {"重量kg": 3200, "壁厚mm": 0.01}), [lax]) == []


def test_file_extension_whitelist() -> None:
    checker = FileExtensionWhitelistChecker()
    rule = _rule("file_extension_whitelist", {"extensions": [".dxf", ".dwg", ".step", ".csv", ".md"]})
    assert checker.supported_extensions() == ()
    assert checker.check(_artifact("SHF-301_revA.step"), [rule]) == []
    # 扩展名大小写不敏感（文件名与清单两侧均不敏感）
    assert checker.check(_artifact("RND-404_revA.STEP"), [rule]) == []
    assert (
        checker.check(_artifact("RND-404_revA.step"), [_rule("file_extension_whitelist", {"extensions": [".STEP"]})])
        == []
    )
    bad = checker.check(_artifact("EXC-302_revA.zip"), [rule])
    assert len(bad) == 1 and bad[0].severity == "error"
    assert bad[0].location == "EXC-302_revA.zip"
    assert "文件扩展名 .zip 不在允许清单" in bad[0].message
    # 无扩展名文件
    none = checker.check(_artifact("README"), [rule])
    assert len(none) == 1 and "文件扩展名 (无) 不在允许清单" in none[0].message
    # 空清单放行（缺配置即跳过）
    assert checker.check(_artifact("a.rar"), [_rule("file_extension_whitelist", {})]) == []


def test_registry() -> None:
    assert set(registered_checkers()) >= {"filename_convention", "metadata_required"}
    assert set(registered_checkers()) == {
        "filename_convention",
        "artifact_code_convention",
        "file_extension_whitelist",
        "metadata_required",
        "metadata_range",
    }
    # 双轨注册表：context 轨道独立于单产物轨道，manifest 汇总两轨并带 kind 标识
    assert set(registered_context_checkers()) == {"bom_consistency", "iteration_completeness"}
    manifest = checker_manifest()
    assert {item["checker_type"] for item in manifest} == set(registered_checkers()) | set(
        registered_context_checkers()
    )
    kinds = {item["checker_type"]: item["kind"] for item in manifest}
    assert kinds["bom_consistency"] == "context"
    assert kinds["iteration_completeness"] == "context"
    assert kinds["metadata_required"] == "artifact"
    assert all(item["description"] for item in manifest)
    assert get_checker("filename_convention") is not None
    assert get_context_checker("bom_consistency") is not None
    with pytest.raises(IterdError) as exc:
        get_checker("nope")
    assert exc.value.code == "ITERD-CHECKER_ERROR"
    with pytest.raises(IterdError) as exc_ctx:
        get_context_checker("metadata_required")
    assert exc_ctx.value.code == "ITERD-CHECKER_ERROR"

    # 双轨重名视为配置错误（两侧互相拦截）
    class _Clash:
        checker_type = "metadata_required"

        def check(self, context: CheckContext, rules: list[RuleRef]) -> list[Finding]:
            return []

    with pytest.raises(IterdError):
        register_context_checker(_Clash())  # type: ignore[arg-type]


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
    out = capsys.readouterr().out
    assert "覆盖式重建完成" in out
    # 覆盖重建：重复执行整体重建，同样成功
    assert main(["seed"]) == 0
    cfg.reset_settings(None)
    dbmod.reset_database()


def test_cli_requires_command() -> None:
    from iterd.cli import _build_parser

    with pytest.raises(SystemExit):
        _build_parser().parse_args([])
