"""命名规范类检查器：文件名 / 产物编码 / 扩展名白名单."""

from __future__ import annotations

import re
from pathlib import Path

from iterd.checkers.registry import ArtifactRef, Finding, RuleRef, register_checker


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


class ArtifactCodeConventionChecker:
    """产物编码规范检查器：按规则 params.pattern 正则校验产物编码."""

    checker_type = "artifact_code_convention"
    description = "按规则 params.pattern 正则校验产物编码"

    def supported_extensions(self) -> tuple[str, ...]:
        """全部文件类型（编码在产物记录上）。"""
        return ()

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in rules:
            pattern = str(rule.params.get("pattern", ""))
            if pattern and not re.match(pattern, artifact.artifact_code):
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        location=artifact.artifact_code,
                        message=f"产物编码 {artifact.artifact_code} 不符合规范 {pattern}",
                    )
                )
        return findings


class FileExtensionWhitelistChecker:
    """扩展名白名单检查器：文件扩展名不在 params.extensions 清单内视为不合规."""

    checker_type = "file_extension_whitelist"
    description = "校验产物文件扩展名是否在 params.extensions 白名单内"

    def supported_extensions(self) -> tuple[str, ...]:
        """全部文件类型（按文件名后缀判定）。"""
        return ()

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        findings: list[Finding] = []
        suffix = Path(artifact.filename).suffix.lower()
        for rule in rules:
            extensions = [str(ext).lower() for ext in rule.params.get("extensions", []) if str(ext).strip()]
            if not extensions or suffix in extensions:
                continue
            findings.append(
                Finding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    location=artifact.filename,
                    message=f"文件扩展名 {suffix or '(无)'} 不在允许清单 {', '.join(extensions)}",
                )
            )
        return findings


register_checker(FilenameConventionChecker())
register_checker(ArtifactCodeConventionChecker())
register_checker(FileExtensionWhitelistChecker())
