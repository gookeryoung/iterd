/** 产物与版本相关 API。 */

import { api } from './client';
import type { Artifact, ArtifactCategory, ArtifactInput, ArtifactVersion } from '../types';

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

/** 产物类别选项（表单用）。 */
export const CATEGORY_OPTIONS: { value: ArtifactCategory; label: string }[] = [
  { value: 'drawing', label: '图纸' },
  { value: 'model', label: '模型' },
  { value: 'spec', label: '规格' },
  { value: 'result', label: '结果' },
];
