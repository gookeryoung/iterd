/** YAML 轻量语法高亮块（等宽字体 + 关键字/字符串/注释着色，GitHub 代码块视觉）。 */

import { useMemo } from 'react';
import { PRIMER_COLORS } from './RunStatusIcon';

/** 词法着色：按行切分，识别注释 / 键 / 列表项 / 引号字符串。 */
function highlightLine(line: string, keyPrefix: number): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // 注释整行
  const commentIndex = line.indexOf('#');
  const code = commentIndex >= 0 ? line.slice(0, commentIndex) : line;
  const comment = commentIndex >= 0 ? line.slice(commentIndex) : '';

  const pattern = /("[^"]*"|'[^']*')|(\s*[-]?\s*[A-Za-z_][\w-]*)(?=\s*:)|(:)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let part = 0;
  while ((match = pattern.exec(code)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(<span key={`${keyPrefix}-p${part++}`}>{code.slice(lastIndex, match.index)}</span>);
    }
    const token = match[0];
    if (match[1]) {
      // 字符串
      nodes.push(
        <span key={`${keyPrefix}-s${part++}`} style={{ color: '#0a3069' }}>
          {token}
        </span>,
      );
    } else if (match[2]) {
      // 键
      nodes.push(
        <span key={`${keyPrefix}-k${part++}`} style={{ color: '#0550ae' }}>
          {token}
        </span>,
      );
    } else {
      // 冒号
      nodes.push(
        <span key={`${keyPrefix}-c${part++}`} style={{ color: PRIMER_COLORS.neutral }}>
          {token}
        </span>,
      );
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < code.length) {
    nodes.push(<span key={`${keyPrefix}-t${part++}`}>{code.slice(lastIndex)}</span>);
  }
  if (comment) {
    nodes.push(
      <span key={`${keyPrefix}-cm`} style={{ color: PRIMER_COLORS.muted }}>
        {comment}
      </span>,
    );
  }
  return nodes;
}

/** YAML 属性。 */
interface YamlBlockProps {
  content: string;
  /** 最大高度（超出滚动）。 */
  maxHeight?: number;
}

export default function YamlBlock({ content, maxHeight = 420 }: YamlBlockProps) {
  const lines = useMemo(() => content.split('\n'), [content]);
  return (
    <div
      style={{
        background: '#f6f8fa',
        border: `1px solid ${PRIMER_COLORS.border}`,
        borderRadius: 6,
        padding: '12px 0',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        fontSize: 12.5,
        lineHeight: '20px',
        overflow: 'auto',
        maxHeight,
      }}
    >
      <div style={{ minWidth: 'max-content' }}>
        {lines.map((line, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              padding: '0 12px',
              whiteSpace: 'pre',
            }}
          >
            <span
              style={{
                width: 36,
                flexShrink: 0,
                textAlign: 'right',
                paddingRight: 12,
                color: PRIMER_COLORS.muted,
                userSelect: 'none',
              }}
            >
              {i + 1}
            </span>
            <span style={{ color: PRIMER_COLORS.text }}>{highlightLine(line, i)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
