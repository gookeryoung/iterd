/** 审批面板：会签进度 + 已签署记录 + 签署弹窗（待办中心与作业详情复用，GitHub 视觉）。 */

import { useState } from 'react';
import { Button, Input, Modal, Progress, Radio, Space, Tag, Typography } from 'antd';
import { CheckOutlined, CloseOutlined, FileDoneOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { recordApproval } from '../../api/workflows';
import { extractErrorMessage } from '../../api/client';
import type { ApprovalDecision, ApprovalEntry, ApprovalInput } from '../../types';
import { APPROVAL_DECISION_LABELS } from '../../types';
import { formatDateTime } from '../../utils/format';
import { PRIMER_COLORS } from './RunStatusIcon';

/** 签署表单值。 */
interface SignFormValues {
  decision: ApprovalDecision;
  comment: string;
}

/** 审批面板属性。 */
interface ApprovalPanelProps {
  /** 作业 id（签署请求目标）。 */
  jobId: number;
  /** 会签门槛（通过所需人数）。 */
  minCount: number;
  /** 当前已通过人数。 */
  approvedCount: number;
  /** 有权签署的主体清单（用户名或角色名）。 */
  approvers: string[];
  /** 已产生的签署记录（按时间升序）。 */
  approvals: ApprovalEntry[];
  /** 当前用户是否可签署。 */
  canApprove: boolean;
  /** 作业是否仍处于等待签署状态。 */
  waiting: boolean;
  /** 签署成功后的额外回调（如失效相关查询）。 */
  onSigned?: () => void;
}

/** 单条签署记录行。 */
function ApprovalEntryRow({ entry }: { entry: ApprovalEntry }) {
  const approved = entry.decision === 'approved';
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 0' }}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 18,
          height: 18,
          borderRadius: '50%',
          flexShrink: 0,
          marginTop: 2,
          background: approved ? PRIMER_COLORS.successBg : PRIMER_COLORS.dangerBg,
        }}
      >
        {approved ? (
          <CheckOutlined style={{ fontSize: 10, color: PRIMER_COLORS.success }} />
        ) : (
          <CloseOutlined style={{ fontSize: 10, color: PRIMER_COLORS.danger }} />
        )}
      </span>
      <div>
        <Space size={8} wrap>
          <Typography.Text strong style={{ fontSize: 12.5 }}>
            {entry.approver_name}
          </Typography.Text>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: approved ? PRIMER_COLORS.success : PRIMER_COLORS.danger,
            }}
          >
            {APPROVAL_DECISION_LABELS[entry.decision]}
          </span>
          <span style={{ fontSize: 11, color: PRIMER_COLORS.neutral }}>
            {formatDateTime(entry.created_at)}
          </span>
        </Space>
        {entry.comment && (
          <div style={{ fontSize: 12.5, color: PRIMER_COLORS.text, marginTop: 2 }}>{entry.comment}</div>
        )}
      </div>
    </div>
  );
}

export default function ApprovalPanel({
  jobId,
  minCount,
  approvedCount,
  approvers,
  approvals,
  canApprove,
  waiting,
  onSigned,
}: ApprovalPanelProps) {
  const { message } = AntApp.useApp();
  const [signOpen, setSignOpen] = useState(false);
  const [form, setForm] = useState<SignFormValues>({ decision: 'approved', comment: '' });

  const signMutation = useMutation({
    mutationFn: (input: ApprovalInput) => recordApproval(jobId, input),
    onSuccess: (record) => {
      message.success(
        record.decision === 'approved'
          ? '签署成功；若达成会签条件，流水线将自动续跑'
          : '已驳回；流水线下游作业将被终止',
      );
      setSignOpen(false);
      setForm({ decision: 'approved', comment: '' });
      onSigned?.();
    },
    onError: (error) => {
      message.error(`签署失败：${extractErrorMessage(error)}`);
    },
  });

  const rejected = approvals.some((a) => a.decision === 'rejected');
  const passed = !waiting && !rejected && approvedCount >= minCount;

  return (
    <div style={{ border: `1px solid ${PRIMER_COLORS.border}`, borderRadius: 6, overflow: 'hidden' }}>
      <div
        style={{
          background: PRIMER_COLORS.canvas,
          borderBottom: `1px solid ${PRIMER_COLORS.border}`,
          padding: '6px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 12,
          fontWeight: 600,
          color: PRIMER_COLORS.text,
        }}
      >
        <FileDoneOutlined />
        会签审批
        {rejected && (
          <Tag color="error" style={{ marginLeft: 'auto', fontSize: 11 }}>
            已驳回
          </Tag>
        )}
        {!rejected && passed && (
          <Tag color="success" style={{ marginLeft: 'auto', fontSize: 11 }}>
            会签达成
          </Tag>
        )}
        {!rejected && waiting && (
          <Tag color="warning" style={{ marginLeft: 'auto', fontSize: 11 }}>
            等待签署
          </Tag>
        )}
      </div>
      <div style={{ padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <Progress
            type="circle"
            size={44}
            percent={Math.min((approvedCount / Math.max(minCount, 1)) * 100, 100)}
            strokeColor={passed ? PRIMER_COLORS.success : rejected ? PRIMER_COLORS.danger : '#9a6700'}
            format={() => `${approvedCount}/${minCount}`}
          />
          <div style={{ fontSize: 12.5, color: PRIMER_COLORS.neutral, lineHeight: 1.7 }}>
            <div>
              会签门槛：需 <strong style={{ color: PRIMER_COLORS.text }}>{minCount}</strong> 人通过，当前{' '}
              <strong style={{ color: PRIMER_COLORS.text }}>{approvedCount}</strong> 人
            </div>
            <div>
              签署范围：
              {approvers.length > 0 ? (
                approvers.map((name) => (
                  <Tag key={name} style={{ fontSize: 11, lineHeight: '18px', marginRight: 4 }}>
                    {name}
                  </Tag>
                ))
              ) : (
                <span>未指定（沿项目树继承）</span>
              )}
            </div>
          </div>
        </div>

        {approvals.length > 0 && (
          <div style={{ borderTop: `1px solid ${PRIMER_COLORS.border}`, paddingTop: 6 }}>
            {approvals.map((entry, i) => (
              <ApprovalEntryRow key={i} entry={entry} />
            ))}
          </div>
        )}

        {waiting && canApprove && (
          <div style={{ marginTop: 8 }}>
            <Button
              type="primary"
              icon={<FileDoneOutlined />}
              loading={signMutation.isPending}
              onClick={() => setSignOpen(true)}
            >
              签署意见
            </Button>
          </div>
        )}
        {waiting && !canApprove && (
          <div style={{ marginTop: 8, fontSize: 12, color: PRIMER_COLORS.neutral }}>
            当前账号不在签署范围内，仅可查看会签进度。
          </div>
        )}
      </div>

      <Modal
        title="签署审批意见"
        open={signOpen}
        okText="提交签署"
        cancelText="取消"
        confirmLoading={signMutation.isPending}
        onOk={() => signMutation.mutate({ decision: form.decision, comment: form.comment.trim() })}
        onCancel={() => {
          setSignOpen(false);
          setForm({ decision: 'approved', comment: '' });
        }}
        destroyOnHidden
      >
        <div style={{ marginBottom: 12 }}>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            决定
          </Typography.Text>
          <Radio.Group
            value={form.decision}
            onChange={(e) => setForm((prev) => ({ ...prev, decision: e.target.value as ApprovalDecision }))}
          >
            <Radio.Button value="approved">
              <CheckOutlined style={{ color: PRIMER_COLORS.success }} /> 通过
            </Radio.Button>
            <Radio.Button value="rejected">
              <CloseOutlined style={{ color: PRIMER_COLORS.danger }} /> 驳回
            </Radio.Button>
          </Radio.Group>
          {form.decision === 'rejected' && (
            <div style={{ marginTop: 8, fontSize: 12, color: PRIMER_COLORS.danger }}>
              驳回将立即终止该流水线：后续作业全部跳过，运行置为失败。
            </div>
          )}
        </div>
        <div>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            意见
          </Typography.Text>
          <Input.TextArea
            rows={3}
            maxLength={500}
            showCount
            placeholder="补充审批说明（可选）"
            value={form.comment}
            onChange={(e) => setForm((prev) => ({ ...prev, comment: e.target.value }))}
          />
        </div>
      </Modal>
    </div>
  );
}
