# S1. 一句话看懂 SafetyHub 在干嘛

> 给非研发同事的开场图。一张图说清"前哨站"在整条 AI 调用链里站在哪一格。

```mermaid
flowchart LR
    User["员工<br/>用 AI 工具提问"]
    Hub["SafetyHub<br/>(前哨站)<br/>看一眼内容"]
    Relay["中转站<br/>(统一对接各厂商)"]
    LLM["大模型<br/>(OpenAI / 国产模型)"]

    User -->|"我的问题"| Hub
    Hub -->|"安全的内容才放行"| Relay
    Relay -->|"按需求选模型"| LLM
    LLM -->|"回答"| Relay
    Relay -->|"回答"| Hub
    Hub -->|"原样转给员工"| User

    classDef user fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef hub fill:#fff3cd,stroke:#b7791f,color:#000
    classDef relay fill:#dff0d8,stroke:#27ae60,color:#000
    classDef llm fill:#ede7f6,stroke:#5e35b1,color:#000
    class User user
    class Hub hub
    class Relay relay
    class LLM llm
```

## 一句话理解

> **SafetyHub 就是公司给 AI 调用加的一道"安全门岗"——员工和大模型之间所有的话，都得先从这里过一道。**

## 它做了三件事

1. **看内容** —— 提问里有没有敏感信息（手机号、客户名、机密项目代号…）
2. **管钥匙** —— 员工不直接拿大模型的 Key，前哨站统一保管和替换
3. **存档案** —— 每一次对话都留底，事后可以查、可以审
