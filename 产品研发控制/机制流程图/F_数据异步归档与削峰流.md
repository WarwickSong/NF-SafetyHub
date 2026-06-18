# F. 数据异步归档与削峰流（落库链路）

> 视角：为什么归档/审计/图片资产写入不会拖慢用户的 `/v1/*` 请求，数据最终是怎么落到 PostgreSQL 的。
> 对应代码：`runtime/archive_queue.py`、`storage/archive.py`、`storage/audit.py`、`storage/image_assets.py`、`storage/training.py`、`storage/data_governance.py`、`proxy/relay.py`。

```mermaid
flowchart TD
    %% ==================== 主链路（同步组装） ====================
    subgraph Hot["主链路 (同步, 必须毫秒级完成)"]
        direction TB
        Req["用户 /v1/chat/completions 请求"]
        Req --> Scan["Scanner 决策<br/>block / desensitize / pass"]
        Scan --> ForwardOrFake["上游转发 或 伪装回复"]
        ForwardOrFake --> StreamCheck{"is_stream ?"}

        StreamCheck -- "非流式" --> AssembleNS["立刻组装 ArchivePayload<br/>request_id / user_id / api_key_id<br/>prompt_original / prompt_desensitized<br/>response (JSON body)<br/>action_taken / matched_rule_ids"]

        StreamCheck -- "流式 SSE" --> Collector["StreamArchiveCollector<br/>逐 chunk 收集到 max_bytes<br/>(截断标记 truncated=True)"]
        Collector --> StreamEnd["流结束 / 上游断开"]
        StreamEnd --> AssembleS["在 _stream_with_archive finally 中<br/>调用 _write_chat_archive"]

        Scan --> AuditAssemble["命中规则时<br/>组装 AuditPayload<br/>(_write_chat_audit)"]

        AssembleNS --> EnqArchive
        AssembleS --> EnqArchive
        AuditAssemble --> EnqAudit

        EnqArchive{"archive_queue.enqueue_archive(payload)"}
        EnqAudit{"archive_queue.enqueue_audit(payload)"}

        EnqArchive -- "put_nowait 成功" --> OKFast["主链路立即返回"]
        EnqArchive -- "QueueFull" --> Drop["dropped += 1<br/>(可观测在 runtime 接口)"]
        Drop --> FallbackTask["asyncio.create_task<br/>fallback 直接调用 ArchiveWriter<br/>(尽力而为)"]
        EnqAudit --> OKFast
    end

    %% ==================== 后台 Worker（异步批量 flush） ====================
    subgraph Cold["后台 worker (ArchiveQueue._run, 单 task)"]
        direction TB
        Loop["while running or 队列非空"]
        Loop --> NextBatch["_next_batch<br/>1) await queue.get() 拿到第 1 条<br/>2) 在 flush_interval_seconds 内<br/>   累计到 batch_size 条"]
        NextBatch --> Split["按 kind 拆分:<br/>archive_payloads / audit_payloads"]

        Split --> WriteArch{"archive_payloads 非空 ?"}
        WriteArch -- "是" --> ArchWriter["ArchiveWriter.write_many<br/>(SQLAlchemy bulk insert)"]
        ArchWriter --> TrainingWriter["TrainingConversationWriter.write_many_from_archive_payloads<br/>仅 passed chat 生成 trajectory"]
        TrainingWriter --> WriteAudit{"audit_payloads 非空 ?"}
        WriteArch -- "否" --> WriteAudit

        WriteAudit -- "是" --> AuditWriter["AuditWriter.write_many<br/>(SQLAlchemy bulk insert)"]
        WriteAudit -- "否" --> TaskDone
        AuditWriter --> TaskDone

        TaskDone["queue.task_done() x N<br/>processed += N<br/>异常被吞 (不影响下一批)"]
        TaskDone --> Loop
    end

    %% ==================== 图片资产异步链路 ====================
    subgraph Image["图片资产 (文生图独立异步链路)"]
        direction TB
        ImgResp["/v1/images/* 响应回来"]
        ImgResp --> ImgMeta["_build_image_metadata<br/>记录 prompt / size / urls / b64 数"]
        ImgMeta --> ImgArchive["ArchivePayload (capability='image')<br/>→ archive_queue (同上)"]

        ImgResp --> ImgSchedule["asyncio.create_task<br/>_schedule_image_asset_archive"]
        ImgSchedule --> Archiver["ImageAssetArchiver"]
        Archiver --> DownLoop["对每个 url/b64:<br/>1. httpx 下载或 base64 解码<br/>2. sha256 + size + mime<br/>3. 写本地 /app/data/images/<br/>4. ImageAsset 行入库"]
        DownLoop --> DBAsset[("image_assets 表")]
    end

    %% ==================== 出口 ====================
    OKFast --> Client["响应回客户端<br/>(延迟 ≈ 上游延迟 + 数毫秒)"]
    AuditWriter --> DBArch
    ArchWriter --> DBArch
    FallbackTask --> DBArch
    DBArch[("PostgreSQL<br/>message_archives<br/>training_conversations<br/>audit_logs")]

    %% ==================== 削峰指标 ====================
    subgraph Snap["snapshot() 暴露给 /admin/api/runtime"]
        S1["queue_size 当前积压"]
        S2["max_size 容量"]
        S3["dropped 累计丢弃"]
        S4["processed 累计落库"]
    end
    Cold -.-> Snap

    %% ==================== 生命周期 ====================
    subgraph Lifecycle["生命周期 (main.lifespan)"]
        Start["app 启动: ArchiveQueue.start()"]
        Stop["app 关闭:<br/>1. running = False<br/>2. await queue.join() 等积压排空<br/>3. cancel worker task"]
    end
    Start -.-> Loop
    Stop -.-> Loop

    classDef hot fill:#fde2e2,stroke:#c0392b,color:#000
    classDef cold fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef img fill:#fff3cd,stroke:#b7791f,color:#000
    classDef db fill:#e8f5e9,stroke:#2e7d32,color:#000
    class Req,Scan,ForwardOrFake,AssembleNS,AssembleS,AuditAssemble,Collector,StreamEnd,OKFast,Drop,FallbackTask hot
    class Loop,NextBatch,Split,ArchWriter,TrainingWriter,AuditWriter,TaskDone cold
    class ImgResp,ImgMeta,ImgArchive,ImgSchedule,Archiver,DownLoop img
    class DBArch,DBAsset db
```

## 关键参数（与 `config.py` 一致）

| 参数 | 默认 | 作用 |
|------|------|------|
| `ARCHIVE_QUEUE_MAX_SIZE` | 5000 | 内存队列上限，超过即 `dropped` |
| `ARCHIVE_BATCH_SIZE` | 50 | 单次 bulk insert 大小 |
| `ARCHIVE_FLUSH_INTERVAL_SECONDS` | 1 | 攒不满批时的最大等待 |
| `ARCHIVE_MAX_PAYLOAD_BYTES` | 262144 | 单条 payload 上限 |
| `STREAM_ARCHIVE_MAX_BYTES` | 见 settings | 流式响应归档截断阈值 |

## 关键设计要点（与代码一致）

- **三段分离**：① Relay 同步组装 payload（CPU 操作，毫秒级）→ ② 投递内存 Queue（`put_nowait`，无阻塞）→ ③ 后台 worker 批量 flush（IO 操作，与主链路解耦）。
- **背压策略**：队列满直接 `dropped += 1`，再 fallback 用 `asyncio.create_task` 尝试一次直写，**不阻塞**用户请求；丢弃数通过 `/admin/api/runtime` 暴露。
- **流式归档**：`StreamArchiveCollector` 不缓存完整响应给用户，只另存一份截断副本到归档，**逐 chunk 仍实时透传给客户端**。
- **批量写入**：`write_many` 用 SQLAlchemy bulk insert，把多次 commit 合并成一次，显著降低 PostgreSQL 压力。
- **训练数据派生**：归档批量写入后，`TrainingConversationWriter` 仅从 `passed` 且未 block 的 Chat 归档派生 `training_conversations`，形成 messages + assistant response 的确定性 `trajectory`，供数据治理覆盖分析和清理使用。
- **优雅关闭**：`stop()` 先 `await queue.join()` 等积压排空再 cancel worker，避免丢数据。
- **图片本体独立异步**：图片下载/解码是慢操作，单独走 `asyncio.create_task` + `ImageAssetArchiver`，不进归档队列，避免拖累文本归档批次。
