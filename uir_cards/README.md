Wendy 包内容说明
================
文件：
- uir_enriched.jsonl：每行一个实体的上下文包（entity + neighbors + retrieved_docs）
- uir_enriched_preview.csv：同上预览版（便于快速浏览）
- scope.yaml：Tier-1/2 映射与抽取范围
- metrics.txt：当前配置下的检索评估（P@k / R@k）
- runs.csv：历史实验汇总（如存在）

关键信息（本次配置）：
- 检索：BM25（索引基于 IFC Schema + Uniclass 语料）
- 参数：k=5，schema_only=1，min_rel=0.45，类匹配启用，类别配额（1×定义 + 2×Pset + 2×QTO）
- 结果：见 metrics.txt（示例：P@5≈0.85，R@5=1.00）

JSONL 结构（uir_enriched.jsonl）：
- entity：{uid, ifc_class, name, attributes, properties, spatial_path, tier_label}
- neighbors：上/下游简单邻接（ContainedIn/Aggregates）
- retrieved_docs：[{doc_id,title,source,path,score,rerank,snippet}, ...]

使用建议：
- 直接把 uir_enriched.jsonl 输入到 LLM 推理模块；对于同一实体的 retrieved_docs 可按 rerank 从高到低拼接或选择前 N 条。
