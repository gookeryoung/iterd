"""artifacts 插件：设计产物、版本、关联."""

from __future__ import annotations

from .models import Artifact, ArtifactLink, ArtifactVersion

__all__ = ["Artifact", "ArtifactLink", "ArtifactVersion"]
