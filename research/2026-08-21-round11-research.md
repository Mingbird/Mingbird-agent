# 永续循环第 11 轮调研(2026-08-21 12:00)
- **Grammar-Constrained Generation**:Ollama `format` 参数在采样层强制 JSON schema,"构造即合法"。警告:①合法 JSON≠正确答案 ②思考模型会穿插 CoT,约束生成可能切掉思考 ③max_tokens 截断。
- Nemotron 3.5 Lightning:专为 agent 执行层训练的小 MoE(30B/3B active)+ 路由库,规划/执行分离。
- 教训:基准前必须调好配置(thinking 关/MTP/上下文/工具 schema),否则得出错误结论。
- LifeOS/edge-agent-lab:小模型路由能力与参数量不成正比,需按案例测试。
- 可测:ollama format 参数能否提升我们三模型的工具调用格式有效性。
- 实测:qwen2b/e2b 加 `format:json` 后都产出合法 tool_calls(参数正确)。但思考模型/流式/长输出需谨慎(可能切 CoT/截断)。列为"待谨慎验证的 harness 增强",不盲改。
