/** 展示格式化工具。 */

import dayjs from 'dayjs';

/** 格式化日期时间为本地可读格式。 */
export function formatDateTime(value?: string | null): string {
  if (!value) {
    return '-';
  }
  return dayjs(value).format('YYYY-MM-DD HH:mm');
}

/** 字节数转可读大小。 */
export function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

/** sha256 前 8 位展示。 */
export function shortSha(sha256: string): string {
  return sha256.slice(0, 8);
}
