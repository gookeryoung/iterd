"""元数据类检查器：必填键类型校验与数值范围校验."""

from __future__ import annotations

from typing import Any

from iterd.checkers.registry import ArtifactRef, Finding, RuleRef, register_checker


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


class MetadataRangeChecker:
    """元数据数值范围检查器：按 params.ranges 校验数值键的上下限.

    缺失键不报（必填职责归 metadata_required）；值非数值（bool 显式排除）记类型问题；
    低于 min 或高于 max 逐键记范围问题；每规则聚合一条发现项。
    """

    checker_type = "metadata_range"
    description = "校验产物元数据数值键的上下限（params.ranges）"

    def supported_extensions(self) -> tuple[str, ...]:
        """全部文件类型（元数据在版本记录上）。"""
        return ()

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in rules:
            ranges = rule.params.get("ranges", {})
            problems: list[str] = []
            for key, spec in ranges.items():
                if key not in artifact.metadata:
                    continue
                value = artifact.metadata[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    problems.append(f"元数据 {key} 应为数值")
                    continue
                minimum = _as_float(spec.get("min")) if isinstance(spec, dict) else None
                maximum = _as_float(spec.get("max")) if isinstance(spec, dict) else None
                if minimum is not None and value < minimum:
                    problems.append(f"元数据 {key} 低于下限 {minimum:g}")
                if maximum is not None and value > maximum:
                    problems.append(f"元数据 {key} 超出上限 {maximum:g}")
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


def _as_float(value: Any) -> float | None:
    """范围边界转数值（None / 非数值 / bool 返回 None 即该侧不约束）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


register_checker(MetadataRequiredChecker())
register_checker(MetadataRangeChecker())
