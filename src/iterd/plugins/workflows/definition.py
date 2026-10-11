"""审查模板 YAML 定义解析与校验（纯函数，无 DB 依赖）。

定义格式对齐 GitHub Actions workflow 语法子集::

    name: 详细设计审查
    description: 静态检查通过后执行仿真

    jobs:
      rules-check:
        name: 静态规则检查
        uses: rules/check
        with:
          rule_set: 机架结构设计规范
      beam-sim:
        name: 横梁静强度仿真
        needs: rules-check
        uses: simulation/run
        with:
          template: BEAM-STATIC-CHECK
          artifact: FRM-002
          inputs: {load: 9000}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, NoReturn

import yaml

# 作业类型（uses 取值）：静态规则检查 / 动态仿真测试
JOB_USES = ("rules/check", "simulation/run")

# job id 约束（对齐 GitHub Actions：小写字母开头，含数字与连字符）
_JOB_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# 顶层允许字段；on 字段为触发器语法兼容预留（解析后忽略）
_TOP_FIELDS = {"name", "description", "jobs", "on"}

# 各 uses 允许的 with 字段
_WITH_FIELDS: dict[str, set[str]] = {
    "rules/check": {"rule_set"},
    "simulation/run": {"template", "artifact", "inputs"},
}

# 各 uses 必填的 with 字段
_WITH_REQUIRED: dict[str, set[str]] = {
    "rules/check": {"rule_set"},
    "simulation/run": {"template"},
}

# job 允许字段
_JOB_FIELDS = {"name", "needs", "uses", "with"}


class WorkflowDefinitionError(ValueError):
    """定义校验失败（消息含定位信息，供 API 422 返回）。"""


@dataclass(frozen=True)
class JobDef:
    """单个作业定义（YAML job 节点的结构化形态）。"""

    key: str
    name: str
    uses: str
    needs: list[str] = field(default_factory=list)
    with_: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowDefinition:
    """审查模板定义（解析结果）。"""

    name: str
    description: str = ""
    jobs: list[JobDef] = field(default_factory=list)

    def job_map(self) -> dict[str, JobDef]:
        """key -> JobDef 映射。"""
        return {job.key: job for job in self.jobs}


def _fail(location: str, message: str) -> NoReturn:
    """抛出带定位的校验错误。"""
    raise WorkflowDefinitionError(f"{location}: {message}")


def parse_definition(text: str) -> WorkflowDefinition:
    """解析并校验 YAML 定义文本。

    Raises:
        WorkflowDefinitionError: 语法错误 / 结构非法 / 引用缺失 / 依赖成环。
    """
    data = _load_yaml_mapping(text)
    _check_top_fields(data)
    jobs = _parse_jobs(data)
    definition = WorkflowDefinition(name=str(data["name"]), description=str(data.get("description", "")), jobs=jobs)
    _validate_refs(definition)
    return definition


def _load_yaml_mapping(text: str) -> dict[str, Any]:
    """加载 YAML 并校验顶层为映射。"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkflowDefinitionError(f"YAML 语法错误: {exc}") from exc
    if not isinstance(data, dict):
        _fail("定义", "顶层必须是映射（name/jobs）")
    return data


def _check_top_fields(data: dict[str, Any]) -> None:
    """校验顶层字段（name/description）。"""
    unknown_top = set(data) - _TOP_FIELDS
    if unknown_top:
        _fail("定义", f"未知顶层字段: {sorted(unknown_top)}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail("name", "必填且须为非空字符串")
    description = data.get("description", "")
    if not isinstance(description, str):
        _fail("description", "须为字符串")


def _parse_jobs(data: dict[str, Any]) -> list[JobDef]:
    """解析并校验 jobs 节点。"""
    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, dict) or not raw_jobs:
        _fail("jobs", "必填且须为非空映射")
    jobs: list[JobDef] = []
    for key, raw in raw_jobs.items():
        jobs.append(_parse_job(key, raw))
    return jobs


def _parse_job(key: Any, raw: Any) -> JobDef:
    """解析并校验单个 job 节点。"""
    if not isinstance(key, str) or not _JOB_KEY_PATTERN.match(key):
        _fail(f"jobs.{key}", "job id 须形如 my-check（小写字母开头，可含数字与连字符）")
    if not isinstance(raw, dict):
        _fail(f"jobs.{key}", "须为映射")
    unknown = set(raw) - _JOB_FIELDS
    if unknown:
        _fail(f"jobs.{key}", f"未知字段: {sorted(unknown)}")
    display = raw.get("name", key)
    if not isinstance(display, str) or not display.strip():
        _fail(f"jobs.{key}.name", "须为非空字符串")
    uses = raw.get("uses")
    if uses not in JOB_USES:
        _fail(f"jobs.{key}.uses", f"仅支持 {' / '.join(JOB_USES)}，当前: {uses!r}")
    needs_raw = raw.get("needs", [])
    if isinstance(needs_raw, str):
        needs_raw = [needs_raw]
    if not isinstance(needs_raw, list) or not all(isinstance(n, str) for n in needs_raw):
        _fail(f"jobs.{key}.needs", "须为字符串或字符串列表")
    with_raw = raw.get("with", {})
    _validate_with(key, uses, with_raw)
    return JobDef(key=key, name=display, uses=uses, needs=list(needs_raw), with_=dict(with_raw))


def _validate_with(key: str, uses: str, with_raw: Any) -> None:
    """校验 with 字段（允许集合 / 必填 / 类型）。"""
    if not isinstance(with_raw, dict):
        _fail(f"jobs.{key}.with", "须为映射")
    allowed = _WITH_FIELDS[uses]
    unknown_with = set(with_raw) - allowed
    if unknown_with:
        _fail(f"jobs.{key}.with", f"未知字段: {sorted(unknown_with)}（{uses} 允许: {sorted(allowed)}）")
    missing = _WITH_REQUIRED[uses] - set(with_raw)
    if missing:
        _fail(f"jobs.{key}.with", f"缺少必填字段: {sorted(missing)}")
    if "rule_set" in with_raw and (
        isinstance(with_raw["rule_set"], bool) or not isinstance(with_raw["rule_set"], (str, int))
    ):
        _fail(f"jobs.{key}.with.rule_set", "须为规则集名称（str）或 id（int）")
    if "template" in with_raw and (
        isinstance(with_raw["template"], bool) or not isinstance(with_raw["template"], (str, int))
    ):
        _fail(f"jobs.{key}.with.template", "须为仿真模板编码（str）或 id（int）")
    if "artifact" in with_raw and not isinstance(with_raw["artifact"], str):
        _fail(f"jobs.{key}.with.artifact", "须为产物编码（str）")
    if "inputs" in with_raw and not isinstance(with_raw["inputs"], dict):
        _fail(f"jobs.{key}.with.inputs", "须为映射")


def _validate_refs(definition: WorkflowDefinition) -> None:
    """校验 needs 引用存在且无环。"""
    keys = set(definition.job_map())
    for job in definition.jobs:
        for dep in job.needs:
            if dep not in keys:
                _fail(f"jobs.{job.key}.needs", f"引用的作业不存在: {dep}")
    layers = topo_layers(definition)
    if sum(len(layer) for layer in layers) != len(definition.jobs):
        _fail("jobs.needs", "依赖关系成环")


def topo_layers(definition: WorkflowDefinition) -> list[list[str]]:
    """Kahn 分层：返回按依赖序排列的作业 key 分层（同层互不依赖）。

    成环时返回的分层覆盖不全（由 :func:`_validate_refs` 在解析期拦截）。
    """
    remaining = {job.key: set(job.needs) for job in definition.jobs}
    layers: list[list[str]] = []
    while remaining:
        ready = sorted(k for k, deps in remaining.items() if not deps)
        if not ready:
            break
        layers.append(ready)
        for k in ready:
            del remaining[k]
        for deps in remaining.values():
            deps.difference_update(ready)
    return layers
