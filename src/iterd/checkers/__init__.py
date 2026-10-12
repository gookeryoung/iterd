"""检查器包：协议、注册表与内置实现.

内置单产物轨道：filename_convention / artifact_code_convention / file_extension_whitelist /
metadata_required / metadata_range；内置跨产物（context）轨道：bom_consistency /
iteration_completeness。新增检查器实现子模块并在底部注册即可，平台代码（规则编排 / 路由）零改动。
"""

from __future__ import annotations

from iterd.checkers.context_checks import BomConsistencyChecker, IterationCompletenessChecker
from iterd.checkers.convention import (
    ArtifactCodeConventionChecker,
    FileExtensionWhitelistChecker,
    FilenameConventionChecker,
)
from iterd.checkers.metadata import MetadataRangeChecker, MetadataRequiredChecker
from iterd.checkers.registry import (
    ArtifactRef,
    BomItemRef,
    CheckContext,
    CheckerAdapter,
    ContextCheckerAdapter,
    Finding,
    RuleRef,
    checker_kind,
    checker_manifest,
    get_checker,
    get_context_checker,
    register_checker,
    register_context_checker,
    registered_checkers,
    registered_context_checkers,
)

__all__ = [
    "ArtifactCodeConventionChecker",
    "ArtifactRef",
    "BomConsistencyChecker",
    "BomItemRef",
    "CheckContext",
    "CheckerAdapter",
    "ContextCheckerAdapter",
    "FileExtensionWhitelistChecker",
    "FilenameConventionChecker",
    "Finding",
    "IterationCompletenessChecker",
    "MetadataRangeChecker",
    "MetadataRequiredChecker",
    "RuleRef",
    "checker_kind",
    "checker_manifest",
    "get_checker",
    "get_context_checker",
    "register_checker",
    "register_context_checker",
    "registered_checkers",
    "registered_context_checkers",
]
