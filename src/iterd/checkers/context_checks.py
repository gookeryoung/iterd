"""跨产物（context）检查器：BOM 一致性与迭代完整性.

context 检查器按迭代执行一次（而非逐产物），输入为 :class:`CheckContext`
（产物集 + BOM + 迭代元数据）。发现项可关联具体产物版本（artifact_version_id），
无关联时为迭代级发现项（如 BOM 缺件，指向 BOM 行而非产物）。
"""

from __future__ import annotations

import re

from iterd.checkers.registry import (
    ArtifactRef,
    BomItemRef,
    CheckContext,
    Finding,
    RuleRef,
    register_context_checker,
)

# BOM 单件重量与产物元数据 重量kg 的默认相对偏差容忍（百分比）
DEFAULT_WEIGHT_TOLERANCE_PCT = 5.0


def _match_artifact(bom: BomItemRef, artifacts: list[ArtifactRef]) -> ArtifactRef | None:
    """BOM 行 → 产物匹配：产物编码精确匹配优先，其次产物元数据 part_code."""
    for artifact in artifacts:
        if artifact.artifact_code == bom.part_code:
            return artifact
    for artifact in artifacts:
        if artifact.metadata.get("part_code") == bom.part_code:
            return artifact
    return None


def _weight_number(value: object) -> float | None:
    """重量取数值（bool / 非数值返回 None 即跳过比对）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class BomConsistencyChecker:
    """BOM 一致性检查器：BOM 零件与产物元数据的编码匹配与重量合理性.

    params.weight_tolerance_pct：单件重量与元数据 重量kg 的相对偏差容忍百分比（默认 5）。
    缺件（BOM 行无对应产物）记迭代级发现项；重量冲突记产物级发现项。
    """

    checker_type = "bom_consistency"
    description = "校验 BOM 零件与产物一致性（编码匹配 / 重量偏差），params.weight_tolerance_pct"

    def check(self, context: CheckContext, rules: list[RuleRef]) -> list[Finding]:
        """对 BOM 全部行执行一致性比对，空 BOM 不产生发现项."""
        findings: list[Finding] = []
        for rule in rules:
            tolerance = rule.params.get("weight_tolerance_pct", DEFAULT_WEIGHT_TOLERANCE_PCT)
            tolerance = float(tolerance) if isinstance(tolerance, (int, float)) else DEFAULT_WEIGHT_TOLERANCE_PCT
            for bom in context.bom_items:
                artifact = _match_artifact(bom, context.artifacts)
                if artifact is None:
                    findings.append(
                        Finding(
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            location=f"bom:{bom.part_code}",
                            message=f"BOM 零件 {bom.part_code}（{bom.part_name}）无对应产物（编码不匹配或缺件）",
                        )
                    )
                    continue
                bom_weight = bom.unit_weight
                meta_weight = _weight_number(artifact.metadata.get("重量kg"))
                if bom_weight is None or meta_weight is None:
                    continue
                base = max(abs(bom_weight), abs(meta_weight))
                deviation = abs(bom_weight - meta_weight) / base * 100 if base else 0.0
                if deviation > tolerance:
                    findings.append(
                        Finding(
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            location=f"bom:{bom.part_code}",
                            artifact_version_id=artifact.version_id,
                            message=(
                                f"BOM 零件 {bom.part_code} 单件重量 {bom_weight:g}kg "
                                f"与产物 {artifact.artifact_code} 元数据 {meta_weight:g}kg "
                                f"偏差 {deviation:.1f}% 超过容忍 {tolerance:g}%"
                            ),
                        )
                    )
        return findings


def _covered_codes(calc: ArtifactRef) -> set[str]:
    """计算书元数据 covers 解析：列表或逗号/顿号分隔字符串（CSV 元数据形态）均支持."""
    covers = calc.metadata.get("covers")
    if isinstance(covers, list):
        return {str(code).strip() for code in covers if str(code).strip()}
    if isinstance(covers, str):
        return {code for code in re.split(r"[,;，；\s]+", covers) if code}
    return set()


class IterationCompletenessChecker:
    """迭代完整性检查器：计算书对指定类别产物的覆盖度.

    params.calc_category：计算书产物类别（默认 result）；
    params.covered_categories：要求被计算书覆盖的产物类别（默认 drawing/model）。
    覆盖关系由计算书元数据 covers（产物编码列表）表达，未覆盖产物逐个记发现项。
    """

    checker_type = "iteration_completeness"
    description = "校验计算书对 drawing/model 产物的覆盖度，params.calc_category / covered_categories"

    def check(self, context: CheckContext, rules: list[RuleRef]) -> list[Finding]:
        """按 covered_categories 逐产物检查计算书覆盖，缺计算书产物记发现项."""
        findings: list[Finding] = []
        for rule in rules:
            calc_category = str(rule.params.get("calc_category", "result"))
            covered_categories = rule.params.get("covered_categories", ["drawing", "model"])
            covered_categories = [str(c) for c in covered_categories]
            calc_artifacts = [a for a in context.artifacts if a.category == calc_category]
            covered_codes: set[str] = set()
            for calc in calc_artifacts:
                covered_codes.update(_covered_codes(calc))
            for artifact in context.artifacts:
                if artifact.category not in covered_categories or artifact.artifact_code in covered_codes:
                    continue
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        location=artifact.artifact_code,
                        artifact_version_id=artifact.version_id,
                        message=f"产物 {artifact.artifact_code}（{artifact.category}）无 {calc_category} 类计算书覆盖",
                    )
                )
        return findings


register_context_checker(BomConsistencyChecker())
register_context_checker(IterationCompletenessChecker())
