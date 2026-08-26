/**
 * 共享 TypeScript 类型.
 *
 * 与后端 Pydantic schema 对齐（参考 docs/design/14-api-specification.md）.
 * 命名约定: 与 Pydantic 模型同名；可选字段使用 `?`；时间统一为 ISO 8601 字符串.
 */

/** 分页响应. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 错误详情（字段级校验信息）.*/
export interface ErrorDetail {
  field?: string;
  message: string;
  code?: string;
  reason?: string;
  value?: unknown;
}

/** 错误响应. */
export interface ErrorResponse {
  code: string;
  message: string;
  details?: Record<string, unknown> | ErrorDetail[];
  request_id?: string;
  timestamp?: string;
  trace_id?: string;
  documentation_url?: string;
}

/** 标准化的前端 Error（来自 axios 响应拦截器）.*/
export interface NormalizedApiError extends Error {
  code: string;
  status?: number;
  details?: Record<string, unknown> | ErrorDetail[];
  request_id?: string;
}

/** Token 对. */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** 用户信息. */
export interface UserInfo {
  user_id: string;
  email: string;
  display_name: string;
  status: string;
  locale: string;
  email_verified_at?: string | null;
  last_login_at?: string | null;
  /** 用户在当前租户的角色列表. */
  tenant_roles?: string[];
}

/** 登录请求/响应. */
export interface LoginRequest {
  email: string;
  password: string;
  tenant_slug: string;
}

export interface LoginResponse {
  tokens: TokenPair;
  user: UserInfo;
  tenant_slug: string;
  role: string;
}

/** ---------- react-flow 节点 / 工作流定义 ---------- */

export interface NodePosition {
  x: number;
  y: number;
}

export interface NodeDef {
  id: string;
  type: string;
  position: NodePosition;
  data?: Record<string, unknown>;
  label?: string | null;
}

export interface EdgeDef {
  id?: string | null;
  source: string;
  target: string;
  source_handle?: string | null;
  target_handle?: string | null;
}

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

export interface WorkflowDefinition {
  nodes: NodeDef[];
  edges: EdgeDef[];
  viewport?: ViewportState | null;
  metadata?: Record<string, unknown> | null;
}

/** ---------- 工作流资源 ---------- */

export interface Workflow {
  id: string;
  name: string;
  description?: string | null;
  tags: string[];
  current_version_number?: number | null;
  definition?: WorkflowDefinition | null;
  versions_count: number;
  runs_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  last_run_at?: string | null;
  last_run_status?: string | null;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  tags: string[];
  definition: WorkflowDefinition;
}

export interface WorkflowUpdate {
  name?: string;
  description?: string;
  tags?: string[];
  definition?: WorkflowDefinition;
  change_summary?: string;
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version_number: number;
  definition: WorkflowDefinition;
  change_summary?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

/** ---------- Run 执行 ---------- */

export type RunStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'cached'
  | 'success'
  | 'failed'
  | 'cancelled'
  | 'retrying';

export interface Run {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  run_number: number;
  status: RunStatus;
  submitted_by: string;
  submitted_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  progress: number;
  inputs_snapshot: Record<string, unknown>;
  metrics: Record<string, unknown>;
  manifest: Record<string, unknown>;
  error?: Record<string, unknown> | null;
  error_summary?: string | null;
  node_executions_count: number;
  created_at: string;
  updated_at: string;
}

export interface RunSubmitRequest {
  workflow_version_id?: string;
  inputs_snapshot?: Record<string, unknown>;
  priority?: number;
  notes?: string;
}

export interface RunCancelResponse {
  run_id: string;
  status: RunStatus;
  cancelled_at: string;
  message: string;
}

/** ---------- 节点执行 ---------- */

export type NodeExecutionStatus =
  | 'pending'
  | 'running'
  | 'cached'
  | 'success'
  | 'failed'
  | 'retrying'
  | 'skipped';

export interface NodeExecution {
  id: string;
  run_id: string;
  node_id: string;
  node_type: string;
  status: NodeExecutionStatus;
  retry_count: number;
  input_hash?: string | null;
  output_hash?: string | null;
  cached_from_run_id?: string | null;
  params: Record<string, unknown>;
  artifact_paths: Record<string, string>;
  error?: Record<string, unknown> | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  logs_count: number;
  created_at: string;
  updated_at: string;
}

/** ---------- 节点契约（节点注册表对外结构）---------- */

export type NodeCategory =
  | '数据接入'
  | 'EDA'
  | '特征工程'
  | '特征筛选'
  | '模型训练'
  | '评分卡与规则'
  | '报告与部署';

export interface PortSchema {
  name: string;
  type: string;
  required: boolean;
  description: string;
  multi?: boolean;
}

export interface ParamChoice {
  label: string;
  value: unknown;
}

export type ParamType =
  | 'str'
  | 'int'
  | 'float'
  | 'bool'
  | 'select'
  | 'multiselect'
  | 'range'
  | 'list'
  | 'dict'
  | 'json'
  | 'file';

export interface ParamSpec {
  name: string;
  type: ParamType;
  label: string;
  description: string;
  default?: unknown;
  required: boolean;
  choices?: ParamChoice[] | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  advanced?: boolean;
  depends_on?: string[];
  placeholder?: string | null;
  help_url?: string | null;
}

export type CacheStrategy = 'by_inputs_hash' | 'by_params_hash' | 'none';

export interface CacheConfig {
  strategy: CacheStrategy;
  ttl_seconds?: number | null;
  trusted_required: boolean;
}

export interface NodeContract {
  node_type: string;
  category: NodeCategory;
  name: string;
  description: string;
  icon: string;
  inputs: PortSchema[];
  outputs: PortSchema[];
  params: ParamSpec[];
  cache: CacheConfig;
  retryable: boolean;
  max_retries: number;
  timeout_sec: number;
  estimated_duration_sec: number;
  tags: string[];
  version: string;
}

export interface NodeDefinition {
  node_type: string;
  category: string;
  name: string;
  description: string;
  icon: string;
  contract_version: string;
  contract: NodeContract;
  enabled: boolean;
  is_custom: boolean;
}

/** ---------- 产物 ---------- */

export type ArtifactType = 'parquet' | 'excel' | 'pmml' | 'json' | 'png' | 'pdf' | 'log' | 'pickle';

export interface Artifact {
  id: string;
  artifact_type: ArtifactType;
  storage_path: string;
  size_bytes: number;
  sha256: string;
  metadata: Record<string, unknown>;
  download_url?: string | null;
  created_at: string;
  updated_at: string;
  /** 节点在 DAG 中的稳定 ID（冗余便于 UI 跳转）.*/
  node_id?: string | null;
  /** 节点类型（如 woe_encoder）.*/
  node_type?: string | null;
  /** 节点中文名（来自 NodeContract.name）.*/
  node_name?: string | null;
  /** 输出端口名（如 binned_df / woe_features）.*/
  output_name?: string | null;
}

export interface ArtifactListResponse {
  artifacts: Artifact[];
}

/** ---------- WebSocket 事件 ---------- */

export interface RunStatusEvent {
  type: 'run_status';
  run_id: string;
  status: RunStatus;
  progress?: number;
  duration_sec?: number;
  total_nodes?: number;
  initial_nodes?: number;
  error_code?: string;
  timestamp?: string;
}

export interface NodeExecutionEvent {
  type: 'node_execution';
  run_id: string;
  node_id: string;
  node_exec_id?: string;
  node_type?: string;
  status: NodeExecutionStatus;
  duration_ms?: number;
  output_hash?: string;
  artifact_keys?: string[];
  retry_count?: number;
  error_code?: string;
  error_message?: string;
  cached_from_run_id?: string;
  timestamp?: string;
}

export interface LogEvent {
  type: 'log';
  run_id: string;
  node_id?: string;
  stream: 'stdout' | 'stderr' | 'system';
  level?: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  ts: number;
}

/** 兜底：未识别事件类型（保留原始 payload 用于调试）.*/
export interface UnknownWSEvent {
  type: string;
  [k: string]: unknown;
}

export type WSEvent = RunStatusEvent | NodeExecutionEvent | LogEvent | UnknownWSEvent;

/** 错误码 → 中文映射（详情页错误消息友好化）.*/
export const ERROR_CODE_MESSAGES: Record<string, string> = {
  E_NODE_NOT_FOUND: '节点类型未注册',
  E_NODE_EXECUTION: '节点执行异常',
  E_AUTH_REQUIRED: '未登录',
  E_AUTH_INVALID: '登录已过期，请重新登录',
  E_TENANT_FORBIDDEN: '无权访问该租户',
  E_FEATURE_NOT_FOUND: '资源不存在',
  E_INVALID_PARAMS: '参数不合法',
  E_VALIDATION_ERROR: '输入校验失败',
  E_STATE_ERROR: '状态不允许',
  E_DEPENDENCY_MISSING: '依赖缺失',
};