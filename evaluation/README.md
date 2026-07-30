# 评测集说明

`cases.jsonl` 包含 60 条离线评测案例：25 条可回答、10 条无依据、10 条澄清、10 条工单工具和 5 条安全案例。

每次修改检索阈值、切分策略、Embedding 或模型提示后，应在相同版本的知识库上重新运行并记录：答案正确率、引用支持率、无依据问题的安全路由率、工具成功率和端到端延迟。不要用虚构数字替代真实结果。

服务启动后运行：

    python evaluation/run.py --base-url http://localhost:8080

报告写入 evaluation/reports/latest/report.json 和 report.md，不包含 API Key。
