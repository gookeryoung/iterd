"""检查器协议、注册表与内置实现.

P0 内置：filename_convention / metadata_required；新增检查器不改平台代码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from iterd.core.errors import IterdError


@dataclass
class ArtifactRef:
    """检查输入：产物版本引用."""

    artifact_id: int
    artifact_code: str
    artifact_name: str
    version_id: int
    version_no: int
    filename: str
    metadata: dict[str, Any]


@dataclass
class RuleRef:
    """检查输入：规则引用."""

    rule_id: int
    code: str
    name: str
    params: dict[str, Any]
    severity: str


@dataclass
class Finding:
    """检查输出."""

    rule_id: int
    severity: str
    location: str
    message: str


class CheckerAdapter(Protocol):
    """静态规则检查器协议：按 checker_type 注册."""

    checker_type: str

    def supported_extensions(self) -> tuple[str, ...]:
        """支持的文件扩展名（空表示全部）。"""

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        """对单个产物执行一组规则，返回发现项."""


_registry: dict[str, CheckerAdapter] = {}


def register_checker(checker: CheckerAdapter) -> None:
    """注册检查器（重复注册覆盖）。"""
    _registry[checker.checker_type] = checker


def get_checker(checker_type: str) -> CheckerAdapter:
    """取检查器，未注册抛 CHECKER_ERROR."""
    if checker_type not in _registry:
        raise IterdError(f"未注册的检查器: {checker_type}", code="ITERD-CHECKER_ERROR", status_code=422)
    return _registry[checker_type]


def registered_checkers() -> list[str]:
    """已注册检查器列表."""
    return sorted(_registry)


def checker_manifest() -> list[dict[str, str]]:
    """检查器清单（供前端下拉选择）：类型 + 说明。"""
    return [
        {"checker_type": name, "description": str(getattr(_registry[name], "description", ""))}
        for name in sorted(_registry)
    ]


class FilenameConventionChecker:
    """文件名规范检查器：按规则 params.pattern 正则校验文件名."""

    checker_type = "filename_convention"
    description = "按规则 params.pattern 正则校验产物文件名"

    def supported_extensions(self) -> tuple[str, ...]:
        """全部文件类型。"""
        return ()

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in rules:
            pattern = str(rule.params.get("pattern", ""))
            if pattern and not re.match(pattern, artifact.filename):
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        location=artifact.filename,
                        message=f"文件名 {artifact.filename} 不符合规范 {pattern}",
                    )
                )
        return findings


class MetadataRequiredChecker:
    """元数据必填检查器：校验 metadata 必填键与类型（str/number/bool）."""

    checker_type = "metadata_required"
    description = "校验产物元数据必填键与类型（str/number/bool）"

    _TYPES = {"str": str, "number": (int, float), "bool": bool}

    def supported_extensions(self) -> tuple[str, ...]:
        """全部文件类型（元数据在版本记录上）。"""
        return ()

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in rules:
            required = rule.params.get("required", {})
            problems: list[str] = []
            for key, expect in required.items():
                type_name = str(expect)
                if key not in artifact.metadata:
                    problems.append(f"缺少必填元数据: {key}")
                elif type_name in self._TYPES and not isinstance(artifact.metadata[key], self._TYPES[type_name]):
                    problems.append(f"元数据 {key} 类型应为 {type_name}")
            if problems:
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        location="metadata",
                        message="; ".join(problems),
                    )
                )
        return findings


register_checker(FilenameConventionChecker())
register_checker(MetadataRequiredChecker())
