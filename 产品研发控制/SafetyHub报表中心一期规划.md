# LLM-SafetyHub 报表中心一期规划

> 本文档是日报、周报、月报与可下载报表文件的一期权威规划。若本文档与阶段 8 旧版“审计 CSV 导出”规划冲突，以本文档为准；阶段 8 中的通用可观测性能力仍保持长期规划口径。

---

## 一、目标与边界

报表中心用于把 SafetyHub 已沉淀的安全审计、请求量、APIKey、Provider 与周期性运行状态采样信息汇总成可归档、可下载、可重复生成的管理报表。

一期范围：

1. 支持日报、周报、月报。
2. 每个周期生成 PDF、XLSX 和 CSV 明细文件。
3. 定时生成为主，管理员手动覆盖重生为辅。
4. 报表文件和元数据保留 3 个月，过期后清理。
5. 报表文件保存到既有 `/app/data` 挂载目录下的 `reports/` 子目录。
6. 失败通过既有 Webhook 通道告警。
7. 仅超级管理员可访问报表中心、生成和下载全局报表。
8. 实现运行状态周期采样，并在日报、周报、月报中展示周期内运行状态统计。

一期不做：

1. 多租户、部门级或普通用户自助报表。
2. 独立下载审计日志。
3. 报表文件永久归档。
4. 引入 Prometheus/Grafana 作为交付依赖。

---

## 二、报表周期

| 类型 | 统计周期 | 自动生成时间 | 说明 |
|------|----------|--------------|------|
| 日报 | 自然日 00:00:00 到 23:59:59 | 每天 02:00 | 生成上一自然日数据 |
| 周报 | 周一 00:00:00 到周日 23:59:59 | 每周一 03:00 | 生成上一完整自然周数据 |
| 月报 | 每月 1 日 00:00:00 到月末 23:59:59 | 每月 1 日 04:00 | 生成上一完整自然月数据 |

统一使用服务器时区 `Asia/Shanghai` 计算周期边界和文件命名。

---

## 三、生成策略

| 场景 | 行为 |
|------|------|
| 定时生成 | 默认不导出敏感字段，生成 PDF、XLSX 和 CSV 明细，成功后更新元数据 |
| 手动生成 | 管理员选择报表类型和周期，可选择是否包含命中片段、脱敏片段、上下文片段 |
| 重复生成 | 同周期、同类型覆盖当前文件与元数据，不保留历史版本 |
| 并发限制 | 对同一报表类型和周期加任务锁，避免定时任务、手动重生或多 worker 重复生成 |
| 失败处理 | 记录失败状态、错误摘要和失败时间，并通过既有 Webhook 配置告警 |
| 清理策略 | 每天执行过期清理，删除超过 3 个月的报表文件和元数据 |

重复生成采用覆盖策略，但元数据应保留最近一次 `generated_at`、`generated_by`、`generation_mode`、`include_sensitive`、`error_message` 和文件 hash，方便判断当前文件来源。

---

## 四、文件与目录

报表目录复用当前 Compose 的 `/app/data` 挂载，默认宿主机路径为 `${SAFETYHUB_DATA_DIR:-./data/app}/reports`。

```text
/app/data/reports/
  daily/
    2026/06/
      safetyhub_daily_2026-06-29.pdf
      safetyhub_daily_2026-06-29.xlsx
      safetyhub_daily_2026-06-29.csv
  weekly/
    2026/W27/
      safetyhub_weekly_2026-W27.pdf
      safetyhub_weekly_2026-W27.xlsx
      safetyhub_weekly_2026-W27.csv
  monthly/
    2026/06/
      safetyhub_monthly_2026-06.pdf
      safetyhub_monthly_2026-06.xlsx
      safetyhub_monthly_2026-06.csv
```

文件名不包含用户、部门、APIKey 明文或其他敏感信息。离线部署包、Compose 示例、`.env.example` 和交付运行手册需要同步说明报表目录、备份和清理规则。

---

## 五、报表内容

### 5.1 PDF

PDF 用于阅读和汇报，应包含：

1. 报表标题、统计周期、生成时间和生成方式。
2. 核心指标卡：总请求次数、安全事件数、拦截数、告警数、脱敏数、通过数。
3. 风险等级分布、动作分布、规则命中 Top、APIKey 调用 Top、Provider 调用摘要。
4. 趋势摘要：日报按 10 分钟聚合、周报按 2 小时聚合、月报按自然日聚合；曲线数据点可较细，但横轴标签必须抽稀展示，避免标签重叠。
5. 高风险事件摘要，默认不展示完整上下文。
6. 周期运行状态曲线和摘要，包括 CPU、内存、磁盘、并发队列、归档队列、上游连接池和健康状态统计；PDF 中曲线优先，数字表格作为辅助说明。

### 5.2 XLSX

XLSX 用于二次分析，建议工作表：

| Sheet | 内容 |
|-------|------|
| 概览 | 周期、生成时间、核心指标、文件敏感标记 |
| 趋势 | 按小时、按日或按周聚合的请求和安全事件趋势 |
| 规则排行 | rule_id、rule_level、scanner_type、action_taken、命中次数 |
| APIKey统计 | api_key_id、请求次数、安全事件数、拦截数、脱敏数 |
| Provider统计 | provider 类型或来源、请求次数、失败摘要，按当前可用字段落地 |
| 高风险明细 | 高风险审计记录摘要，是否包含敏感字段由生成参数决定 |
| 系统状态 | 周期内运行状态采样明细和聚合数据，包括曲线原始点、平均值、峰值、最低可用空间和异常采样次数 |

### 5.3 CSV

CSV 一期定位为安全事件明细导出，不承载多 Sheet 汇总。默认字段包括时间、request_id、user_id、api_key_id、rule_id、rule_level、scanner_type、action_taken、model、provider 摘要和审计 ID。

定时生成默认不包含 `matched_snippet`、`redacted_snippet`、`context_before`、`context_after`。手动生成时管理员可显式选择包含这些字段，并在元数据中标记 `include_sensitive=true`。

---

## 六、数据口径

| 指标 | 建议来源 | 口径 |
|------|----------|------|
| 总请求次数 | `training_conversations` 加 `audit_logs` 或现有统计读模型 | 周期内进入 SafetyHub 的 Chat 安全治理请求总次数，避免只把命中审计当总请求 |
| 安全事件数 | `audit_logs` | 周期内审计事件数量 |
| 拦截数 | `audit_logs.action_taken = blocked` | 周期内被伪装拦截的请求数量 |
| 脱敏数 | `audit_logs.action_taken = desensitized` | 周期内发生请求侧脱敏的请求数量 |
| 告警数 | `audit_logs.action_taken = warn` 或后续告警表 | 一期按审计动作统计，Webhook 告警失败不反向改变审计口径 |
| 通过数 | `training_conversations` 或现有统计口径 | 周期内通过并沉淀的请求数量 |
| APIKey统计 | `training_conversations.api_key_id`、`audit_logs.api_key_id`、`api_keys` | 按当前已落库字段聚合，不展示完整 Key |
| Provider统计 | APIKey Provider 字段或 KeyProvider 配置 | 以当前可稳定获取字段为准，不为报表强行引入上游实时调用 |
| 系统运行状态 | 新增运行状态采样表，采样来源包括 `/admin/api/runtime` 同源内部方法、健康检查、磁盘空间和 `psutil` | 周期内按采样数据统计平均值、最小值、峰值、异常次数和可用空间变化 |

总请求次数可行，但需要明确不能只读 `audit_logs`，因为 `audit_logs` 主要代表安全事件；完整总请求更适合结合 `training_conversations` 和已有统计接口口径实现。

### 6.1 运行状态采样口径

报表中的系统运行状态不使用“生成时状态”，而是基于报表周期内的采样数据聚合。

| 采样项 | 建议来源 | 报表聚合口径 |
|--------|----------|--------------|
| 服务健康 | 应用内部 ready 检查或等价健康函数 | 健康采样次数、异常采样次数、异常占比 |
| CPU 使用率 | `psutil.cpu_percent()` | 平均值、最小值、峰值 |
| 内存使用率 | `psutil.virtual_memory()` | 平均值、最小值、峰值 |
| 数据目录磁盘 | `shutil.disk_usage(settings.data_disk_monitor_path)` | 最低剩余空间、最高使用率 |
| 系统磁盘 | 既有 `system_disk_monitor_container_path` | 最低剩余空间、最高使用率 |
| `/v1` 并发队列 | `get_v1_concurrency_snapshot()` | 平均排队数、最小排队数、最大排队数、拒绝数增量、超时数增量 |
| 归档队列 | `ArchiveQueue.snapshot()` | 平均队列长度、最小队列长度、最大队列长度、处理数增量、丢弃数增量 |
| 上游连接池 | 既有上游连接池配置和错误统计 | 配置摘要、上游错误数增量，若当前无错误计数字段则先留空 |

采样频率建议默认 5 分钟一次，可通过配置调整。PDF 报表应优先用曲线展示运行状态变化：日报按 10 分钟聚合，横轴只显示小时坐标；周报按 2 小时聚合，横轴抽稀显示日期；月报按自然日聚合，横轴只显示日。运行状态曲线默认展示均值趋势，摘要表展示均值、最小值和峰值；磁盘容量保留在容量摘要中展示周期内最低空闲，不塞入主曲线。XLSX 保留曲线数据点和聚合表。采样任务失败不影响 `/v1` 主链路，失败次数进入报表和告警摘要。

---

## 七、接口规划

| 接口 | 方法 | 用途 |
|------|------|------|
| `/admin/api/reports` | GET | 查询报表列表，支持类型、周期、状态筛选 |
| `/admin/api/reports/generate` | POST | 手动生成或覆盖重生指定周期报表 |
| `/admin/api/reports/{report_id}` | GET | 查看报表元数据和生成状态 |
| `/admin/api/reports/{report_id}/download?format=pdf|xlsx|csv` | GET | 下载指定格式文件 |
| `/admin/api/reports/{report_id}/retry` | POST | 对失败报表重试生成 |
| `/admin/api/reports/pdf-preview` | POST | 开发评估阶段生成 PDF 样式预览，用于比较依赖方案 |
| `/admin/api/reports/runtime-samples/summary` | GET | 查询运行状态采样摘要，用于报表中心调试和验收 |

所有接口必须复用管理员认证和超级管理员权限判断。下载接口不得直接暴露静态文件目录。

---

## 八、数据模型规划

建议新增 `report_jobs` 或 `generated_reports` 表：

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| report_type | daily / weekly / monthly |
| period_start | 周期开始时间 |
| period_end | 周期结束时间 |
| timezone | 默认 Asia/Shanghai |
| status | pending / running / succeeded / failed |
| generation_mode | scheduled / manual |
| include_sensitive | 是否包含敏感明细字段 |
| pdf_path / xlsx_path / csv_path | 相对 `/app/data/reports` 的文件路径 |
| pdf_sha256 / xlsx_sha256 / csv_sha256 | 文件 hash |
| summary_json | 核心指标摘要 |
| runtime_summary_json | 周期内运行状态采样聚合摘要 |
| error_message | 失败摘要 |
| generated_by | scheduled 或管理员用户名 |
| generated_at | 生成完成时间 |
| expires_at | 文件和元数据过期时间 |
| created_at / updated_at | 记录创建和更新时间 |

唯一约束建议覆盖 `report_type + period_start + period_end`，用于配合覆盖重生和并发锁。

建议新增 `runtime_samples` 表：

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| sampled_at | 采样时间，统一保存 timezone-aware UTC，展示时转 `Asia/Shanghai` |
| worker_pid | 当前 worker pid |
| health_status | healthy / degraded / unhealthy |
| cpu_percent | CPU 使用率 |
| memory_percent | 内存使用率 |
| data_disk_total / data_disk_used / data_disk_free | 数据目录磁盘空间 |
| system_disk_total / system_disk_used / system_disk_free | 系统磁盘空间 |
| v1_inflight / v1_queued | `/v1` 当前在途和排队数 |
| v1_rejected_total / v1_timeout_total | `/v1` 拒绝和超时累计计数 |
| archive_queue_size | 归档队列长度 |
| archive_processed_total / archive_dropped_total | 归档处理和丢弃累计计数 |
| upstream_error_total | 上游错误累计计数，当前无法稳定采集时可为空 |
| raw_json | 保留扩展字段，禁止写入 prompt、response、APIKey 明文或密钥 |
| created_at | 记录创建时间 |

采样表保留周期与报表一致为 3 个月。清理任务同时清理过期报表文件、报表元数据和运行状态采样数据。

---

## 九、运行状态采样实现建议

建议新增依赖：

| 依赖 | 用途 | 说明 |
|------|------|------|
| `psutil` | 采集 CPU、内存、进程和磁盘辅助信息 | Python 生态常用系统监控库，适合容器内轻量采样 |
| `APScheduler` | 定时报表、运行状态采样和过期清理 | 比手写后台循环更规范，支持 cron 触发和时区配置 |

不建议一期引入 Docker SDK 或挂载 Docker socket。容器内读取 Docker socket 会扩大权限边界，且当前报表需要的是 SafetyHub 自身运行质量，不需要控制宿主机 Docker。

Prometheus/Grafana 仍可作为后续外部监控增强，但不作为报表中心一期交付依赖。

---

## 十、PDF 方案评估

正式开发前需要实际测试两个候选方案并给出样例效果：

| 方案 | 优点 | 风险 |
|------|------|------|
| HTML 模板 + WeasyPrint | 排版接近网页，适合美观报表，模板维护直观 | Linux 系统依赖、中文字体和离线镜像体积需要验证 |
| ReportLab | Python 依赖相对直接，可控性强，适合离线环境 | 复杂排版和中文样式成本高，图表和表格美观度需要额外处理 |

如果 WeasyPrint 在当前 Docker/离线环境依赖过重，则一期可优先采用 ReportLab 做稳定版，再把 HTML 转 PDF 作为美化增强。

---

## 十一、验收标准

- [ ] 管理员可在报表中心查看日报、周报、月报列表和生成状态。
- [ ] 系统按 02:00、03:00、04:00 自动生成上一周期日报、周报、月报。
- [ ] 管理员可手动覆盖重生指定周期报表，并选择是否包含敏感明细字段。
- [ ] 每份成功报表可下载 PDF、XLSX 和 CSV。
- [ ] 定时生成的 CSV/XLSX 不包含命中片段、脱敏片段和上下文片段。
- [ ] 同一类型同一周期不会并发生成多份互相覆盖的文件。
- [ ] 生成失败会记录失败状态并触发 Webhook 告警。
- [ ] 超过 3 个月的报表文件和元数据会被清理。
- [ ] 系统按配置周期采集运行状态，并在日报、周报、月报中展示周期内聚合结果。
- [ ] 运行状态采样数据保留 3 个月，过期后随报表清理任务清理。
- [ ] Docker 和离线部署说明包含报表目录、备份、恢复和清理规则。
