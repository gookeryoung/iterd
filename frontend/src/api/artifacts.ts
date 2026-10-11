/** 产物与版本相关 API。 */

import { api } from './client';
import type {
  Artifact,
  ArtifactCategory,
  ArtifactInput,
  ArtifactLink,
  ArtifactLinkInput,
  ArtifactUpdateInput,
  ArtifactVersion,
  LinkType,
} from '../types';

/** 产物列表（iteration_id / project_id 至少一个）。 */
export async function fetchArtifacts(params: {
  iteration_id?: number;
  project_id?: number;
}): Promise<Artifact[]> {
  const resp = await api.get<Artifact[]>('/artifacts', { params });
  return resp.data;
}

/** 创建产物（后端 201）。 */
export async function createArtifact(
  iterationId: number,
  data: ArtifactInput,
): Promise<Artifact> {
  const resp = await api.post<Artifact>('/artifacts', data, {
    params: { iteration_id: iterationId },
  });
  return resp.data;
}

/** 产物版本历史。 */
export async function fetchVersions(artifactId: number): Promise<ArtifactVersion[]> {
  const resp = await api.get<ArtifactVersion[]>(`/artifacts/${artifactId}/versions`);
  return resp.data;
}

/** 上传新版本（multipart：file + note + metadata JSON 字符串）。 */
export async function uploadVersion(
  artifactId: number,
  args: { file: File; note?: string; metadata?: string },
): Promise<ArtifactVersion> {
  const form = new FormData();
  form.append('file', args.file);
  form.append('note', args.note ?? '');
  if (args.metadata && args.metadata.trim().length > 0) {
    form.append('metadata', args.metadata.trim());
  }
  const resp = await api.post<ArtifactVersion>(`/artifacts/${artifactId}/versions`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return resp.data;
}

/** 下载版本内容（axios blob 携带认证头）。 */
export async function downloadVersion(versionId: number, fallbackName: string): Promise<void> {
  const resp = await api.get<Blob>(`/versions/${versionId}/download`, { responseType: 'blob' });
  // 优先从 Content-Disposition 解析文件名
  const disposition = String(resp.headers['content-disposition'] ?? '');
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(resp.data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** 更新产物基本信息（名称/描述/类别/元数据）。 */
export async function updateArtifact(id: number, data: ArtifactUpdateInput): Promise<Artifact> {
  const resp = await api.patch<Artifact>(`/artifacts/${id}`, data);
  return resp.data;
}

/** 软删产物（reviewer+）。 */
export async function deleteArtifact(id: number): Promise<void> {
  await api.delete(`/artifacts/${id}`);
}

/** 产物关联列表（双向，含对端编码/名称）。 */
export async function fetchLinks(artifactId: number): Promise<ArtifactLink[]> {
  const resp = await api.get<ArtifactLink[]>(`/artifacts/${artifactId}/links`);
  return resp.data;
}

/** 创建产物关联。 */
export async function createLink(
  artifactId: number,
  data: ArtifactLinkInput,
): Promise<ArtifactLink> {
  const resp = await api.post<ArtifactLink>(`/artifacts/${artifactId}/links`, data);
  return resp.data;
}

/** 删除产物关联。 */
export async function deleteLink(artifactId: number, linkId: number): Promise<void> {
  await api.delete(`/artifacts/${artifactId}/links/${linkId}`);
}

/** 预览版本内容（返回 Blob 与 content-type，便于前端按类型渲染）。 */
export async function previewVersion(
  versionId: number,
): Promise<{ blob: Blob; contentType: string }> {
  const resp = await api.get<Blob>(`/versions/${versionId}/preview`, { responseType: 'blob' });
  return { blob: resp.data, contentType: String(resp.headers['content-type'] ?? '') };
}

/** 关联类型选项。 */
export const LINK_TYPE_OPTIONS: { value: LinkType; label: string }[] = [
  { value: 'part_of', label: '组成（part_of）' },
  { value: 'refers_to', label: '引用（refers_to）' },
  { value: 'derived_from', label: '派生（derived_from）' },
];

/** 产物类别选项（表单用）。 */
export const CATEGORY_OPTIONS: { value: ArtifactCategory; label: string }[] = [
  { value: 'drawing', label: '图纸' },
  { value: 'model', label: '模型' },
  { value: 'spec', label: '规格' },
  { value: 'result', label: '结果' },
];
