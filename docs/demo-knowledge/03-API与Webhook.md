# API 与 Webhook

## API 基础规则

FlowPilot API 使用 HTTPS 和 JSON。请求必须携带 `Authorization: Bearer <token>`，但客户不得在聊天、截图或工单中提交完整 Token。默认限流为每个工作空间每分钟 600 次请求。

所有写入接口支持 `Idempotency-Key` 请求头。相同工作空间在 24 小时内重复使用同一幂等键时，系统返回第一次请求的结果，不重复创建资源。

## 错误码 API-42901

`API-42901` 表示工作空间超过分钟级调用配额。响应头 `Retry-After` 给出建议等待秒数。客户端应采用指数退避并加入随机抖动，不能立即无限重试。

如果调用量明显低于套餐配额，请记录请求时间段、工作空间编号和响应中的追踪编号后提交 API/集成类工单。

## Webhook 签名失败

接收方应使用原始请求体和 Webhook Secret 计算 HMAC-SHA256，不要先解析并重新序列化 JSON。签名头为 `X-FlowPilot-Signature`，时间戳头为 `X-FlowPilot-Timestamp`。

错误码 `WH-40007` 表示签名校验失败。常见原因是 Secret 使用错误、代理修改请求体、服务器时间偏差超过 5 分钟。轮换 Secret 后，旧 Secret 保留 10 分钟过渡期。
