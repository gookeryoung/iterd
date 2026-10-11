"""检查器包：协议、注册表与内置实现.

内置：filename_convention / artifact_code_convention / file_extension_whitelist /
metadata_required / metadata_range；新增检查器实现子模块并在底部注册即可，
平台代码（规则编排 / 路由）零改动。
"""

from __future__ import annotations

from iterd.checkers.convention import (
    ArtifactCodeConventionChecker,
    FileExtensionWhitelistChecker,
    FilenameConventionChecker,
)
from iterd.checkers.metadata import MetadataRangeChecker, MetadataRequiredChecker
from iterd.checkers.registry import (
    ArtifactRef,
    CheckerAdapter,
    Finding,
    RuleRef,
    checker_manifest,
    get_checker,
    register_checker,
    registered_checkers,
)

__all__ = [
    "ArtifactCodeConventionChecker",
    "ArtifactRef",
    "CheckerAdapter",
    "FileExtensionWhitelistChecker",
    "FilenameConventionChecker",
    "Finding",
    "MetadataRangeChecker",
    "MetadataRequiredChecker",
    "RuleRef",
    "checker_manifest",
    "get_checker",
    "register_checker",
    "registered_checkers",
]
