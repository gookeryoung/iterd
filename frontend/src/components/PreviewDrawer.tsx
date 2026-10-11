/** 版本在线预览抽屉：图片直出 / PDF iframe / Markdown 渲染 / 纯文本展示。 */

import { useEffect, useState } from 'react';
import { Alert, Drawer, Spin, Typography } from 'antd';
import { marked } from 'marked';
import { previewVersion } from '../api/artifacts';
import { extractErrorMessage } from '../api/client';
import { formatSize } from '../utils/format';

/** 预览抽屉属性。 */
interface PreviewDrawerProps {
  versionId: number | null;
  filename: string;
  size: number;
  onClose: () => void;
}

/** 预览状态。 */
interface PreviewState {
  loading: boolean;
  error: string;
  url: string | null;
  kind: 'image' | 'pdf' | 'text' | null;
  text: string;
}

export default function PreviewDrawer({ versionId, filename, size, onClose }: PreviewDrawerProps) {
  const [state, setState] = useState<PreviewState>({
    loading: false,
    error: '',
    url: null,
    kind: null,
    text: '',
  });

  useEffect(() => {
    if (versionId === null) {
      setState({ loading: false, error: '', url: null, kind: null, text: '' });
      return;
    }
    let revoked = false;
    let objectUrl: string | null = null;
    setState({ loading: true, error: '', url: null, kind: null, text: '' });

    void (async () => {
      try {
        const { blob, contentType } = await previewVersion(versionId);
        const isText = contentType.startsWith('text/');
        if (isText) {
          const text = await blob.text();
          if (!revoked) {
            setState({ loading: false, error: '', url: null, kind: 'text', text });
          }
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        if (revoked) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setState({
          loading: false,
          error: '',
          url: objectUrl,
          kind: contentType.startsWith('image/') ? 'image' : 'pdf',
          text: '',
        });
      } catch (error: unknown) {
        if (!revoked) {
          setState({ loading: false, error: extractErrorMessage(error), url: null, kind: null, text: '' });
        }
      }
    })();

    return () => {
      revoked = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [versionId, filename]);

  return (
    <Drawer
      title={`预览 - ${filename}`}
      width={900}
      open={versionId !== null}
      onClose={onClose}
      destroyOnClose
    >
      {state.loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
        </div>
      )}
      {state.error && <Alert type="error" showIcon message="预览失败" description={state.error} />}
      {state.kind === 'image' && state.url && (
        <img src={state.url} alt={filename} style={{ maxWidth: '100%' }} />
      )}
      {state.kind === 'pdf' && state.url && (
        <iframe src={state.url} title={filename} style={{ width: '100%', height: '75vh', border: 'none' }} />
      )}
      {state.kind === 'text' && (
        <div style={{ maxHeight: '75vh', overflow: 'auto' }}>
          <Typography.Paragraph type="secondary">
            {filename}（{formatSize(size)}）
          </Typography.Paragraph>
          {isMarkdownHint(filename) ? (
            <div
              className="iterd-markdown-body"
              // Markdown 由后端文件渲染，内容受项目内权限控制
              dangerouslySetInnerHTML={{ __html: marked.parse(state.text) as string }}
            />
          ) : (
            <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{state.text}</pre>
          )}
        </div>
      )}
      {!state.loading && !state.error && state.kind === null && versionId !== null && (
        <Typography.Text type="secondary">该版本暂无可预览内容</Typography.Text>
      )}
    </Drawer>
  );
}

/** 依据扩展名判断是否按 Markdown 渲染。 */
function isMarkdownHint(filename: string): boolean {
  return /\.md$/i.test(filename) || /\.markdown$/i.test(filename);
}
