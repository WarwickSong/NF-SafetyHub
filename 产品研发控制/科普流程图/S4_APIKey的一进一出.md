# S4. APIKey 的一进一出

> 为什么员工拿到的 Key 和真正打到中转站的 Key 不是同一个——这件事一张图说清。

```mermaid
flowchart LR
    subgraph Outside["员工看到的"]
        UserKey["SafetyHub Key<br/>sk-safetyhub-xxxx<br/>(发给员工的工牌)"]
    end

    subgraph Inside["前哨站内部 (员工看不到)"]
        Vault["加密金库<br/>🔒 Fernet 加密存储"]
        RealKey["真正的中转站 Key<br/>sk-yxai-yyyy"]
        Vault --- RealKey
    end

    subgraph Upstream["中转站收到的"]
        UpKey["看到的是真正的中转站 Key<br/>sk-yxai-yyyy"]
    end

    UserKey -.->|"员工请求带着这个 Key"| Door["前哨站门口<br/>核对身份"]
    Door -->|"查金库 → 取出对应的真 Key"| Vault
    Vault -->|"换上真 Key"| UpKey

    classDef outside fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef inside fill:#fff3cd,stroke:#b7791f,color:#000
    classDef upstream fill:#dff0d8,stroke:#27ae60,color:#000
    class UserKey outside
    class Vault,RealKey,Door inside
    class UpKey upstream
```

## 为什么要这么绕

| 场景 | 好处 |
|------|------|
| 员工离职 | 后台一键吊销他的 Key，不影响别人 |
| Key 泄露 | 只需替换"真 Key"，员工那张工牌不用换 |
| 成本分摊 | 每个 Key 绑定部门/成本中心，账单可以拆 |
| 安全审计 | 真 Key 永远只在内存里出现一瞬间，落库和日志都是密文 |

## 一个比喻

> SafetyHub Key 像**公司给员工的门禁卡**——刷一下就能用。
> 中转站 Key 像**大楼真正的物理钥匙**——锁在保险柜里，门禁系统替员工去开门。
> 员工根本不需要知道真钥匙长什么样。
