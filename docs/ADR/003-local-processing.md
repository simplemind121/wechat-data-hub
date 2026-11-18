# ADR 003 — 本地图片/语音/AI 处理与来源证据

日期：2026-11-18。OCR首先交付；语音/语义/LLM按后续任务分别验收，不用提供方模拟测试冒充真实模型。

OCR使用Tesseract（Apache-2.0）+固定SHA的tessdata_fast中文/英文模型（Apache-2.0），Pillow 13.0（MIT-CMU）验证像素/格式并生成私有临时PNG，不覆盖原图。输出TSV逐词文字、原图像素坐标、原始算法评分；模型/引擎/处理版本进入幂等键。同一图可服务不同消息，每条结果保留明确message/attachment/hash来源。只支持PNG/JPEG/WebP/静态GIF，动画和PDF不假称已支持。空白图可返回零识别字，不凭空生成结果。

所有调用为固定argv、无shell、最小子进程环境、受限输出/时间、受限图片字节和像素。模型目录仅由本地管理员管理；字节SHA绑定结果，原件不可变。处理结果单独保存，不改写规范消息body；关键词可命中派生文字并明确标注。网页提供原图词框定位、结果/版本导出、失败/取消和重试。关闭模块撤销排队/运行任务的写入资格；fencing token在计算后再次验证。长计算不持有数据库行锁。

新增processing_policies是管理员明确启用的workspace配置，默认沿用关闭的环境开关；可在网页单独启用本地模块。配置隔离于用户/角色。processing_results带workspace复合外键与job唯一，reader可查看自己workspace的结果，只有reviewer/admin可发起，只有admin可启停/重试。关闭保留已有结果及原件。原有加密备份按表清单自动包含新结果和策略；恢复仍严格匹配schema版本。

采用的可选CPU依赖：sherpa-onnx 2.0.1（Apache-2.0，维护中的ONNX本地语音推理，Whisper量化模型MIT）、soundfile（BSD-3-Clause，libsndfile LGPL-2.1-or-later，通过独立动态库提供）、numpy（BSD-3-Clause）、httpx（BSD-3-Clause）。避免安装PyTorch/GPU运行时。模型文件不因核心应用启动而隐式下载；来源、精确SHA与许可随model_assets.json记录。额外依赖锁在ai可选组，尚无模型时报告not ready，不影响核心归档。

候选AI/业务字段仍需精确原文跨度和人工审批；OCR/ASR识别评分不等于事实可信度。默认零云推理调用。未授权实例不执行真实Odoo写入；真实导出器/设备矩阵独立验证。

语义/LLM 使用 llama.cpp b12488 固定 Ubuntu x64 CPU 运行包（MIT），SHA 与源码提交10152bc4a05742202dd24ee35352161ca84a7964以及上游许可随包保存。使用独立 native server 子进程，临时回环监听/随机访问密钥、禁用Web UI/日志/代理继承；不加载不兼容的musl Python轮子。不引入PyTorch或Python llama-cpp扩展。BGE-small-zh-v1.5 Q8模型MIT，Qwen2.5-0.5B Q4_K_M模型Apache-2.0。pgvector0.8.7（PostgreSQL许可）从固定源码提交构建，与PG17.6头文件匹配，禁用CPU特化/LLVM；只在显式启用语义功能时创建扩展和缓存schema。为权限正确性使用作用域内精确余弦，并融合独立关键词候选，不承诺十万条语义查询性能。

发布审计发现Pillow12.3存在公开漏洞，已升级13.0.0并重跑OCR/恢复/浏览器回归及运行依赖审计。不用输入格式白名单作为拒绝升级的理由。小型LLM可能输出空候选、错误跨度或遗漏实体，服务端过滤、明确展示并强制人工审核；无模型准确率承诺。
