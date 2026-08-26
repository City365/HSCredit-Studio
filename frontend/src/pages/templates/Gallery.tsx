/**
 * 模板库 — 卡片网格展示可用工作流模板.
 *
 * 通过 templatesApi 加载系统模板 + 当前租户私有模板.
 * 点击「立即使用」调用 instantiate API 创建工作流并跳转.
 */

import { Card, Row, Col, Button, Rate, Tag, Input, Typography, Empty, Spin } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { templatesApi, type Template } from '@/api/templates';
import { useApiMutation, useApiQuery } from '@/hooks/useApi';

const CATEGORY_ICON: Record<string, string> = {
  '评分卡': '💳',
  '规则': '⛏️',
  '监控': '📡',
  'EDA': '🔍',
  '模型训练': '📈',
  '特征工程': '➕',
  '报告': '📋',
};

export default function TemplateGalleryPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [page] = useState(1);

  const { data, isLoading } = useApiQuery(
    ['templates', page, search],
    templatesApi.list,
    { page, page_size: 24, search },
  );

  const instantiate = useApiMutation(
    (templateId: string) => templatesApi.instantiate(templateId, {}),
    {
      onSuccess: (workflow) => {
        navigate(`/workflows/${workflow.id}`);
      },
    },
  );

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <Typography.Title level={4}>模板库</Typography.Title>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Input.Search
          placeholder="搜索模板"
          allowClear
          onSearch={setSearch}
          style={{ width: 300 }}
        />
        <span style={{ color: '#999' }}>共 {total} 个模板</span>
      </div>
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : items.length === 0 ? (
        <Empty description="暂无模板" />
      ) : (
        <Row gutter={[16, 16]}>
          {items.map((tpl: Template) => {
            const icon = tpl.icon ?? CATEGORY_ICON[tpl.category] ?? '📦';
            const pending = instantiate.isPending && instantiate.variables === tpl.id;
            return (
              <Col key={tpl.id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  cover={
                    <div
                      style={{
                        height: 120,
                        background: '#fafafa',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 48,
                      }}
                    >
                      {icon}
                    </div>
                  }
                  actions={[
                    <Button
                      key="use"
                      type="primary"
                      loading={pending}
                      onClick={() => instantiate.mutate(tpl.id)}
                    >
                      立即使用
                    </Button>,
                  ]}
                >
                  <Card.Meta
                    title={
                      <div>
                        {tpl.name}
                        {tpl.is_system && (
                          <Tag color="blue" style={{ marginLeft: 4 }}>
                            系统
                          </Tag>
                        )}
                      </div>
                    }
                    description={
                      <div>
                        <Tag>{tpl.category}</Tag>
                        <p style={{ marginTop: 8, minHeight: 40 }}>{tpl.description}</p>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginTop: 8,
                          }}
                        >
                          <Rate
                            disabled
                            allowHalf
                            value={tpl.rating_avg}
                            style={{ fontSize: 14 }}
                          />
                          <span style={{ color: '#999', fontSize: 12 }}>
                            {tpl.use_count} 次使用
                          </span>
                        </div>
                      </div>
                    }
                  />
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
    </div>
  );
}