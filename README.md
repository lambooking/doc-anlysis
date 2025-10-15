# 文档智能审核系统

基于 Qwen-2.5-VL 7B 的文档智能审核系统，支持作业指导书和风险管控方案的自动化审核，在 120 秒内完成审核并输出带批注的文档和详细报告。

## 功能特性

- ✅ **多格式支持**：支持 PDF、DOCX、DOC 文档格式
- ✅ **智能审核**：基于 Qwen-2.5-VL 7B 多模态大模型进行文档理解
- ✅ **规则驱动**：支持 YAML 配置的灵活审核规则
- ✅ **精确批注**：在原文档上高亮标注问题位置，添加详细批注
- ✅ **详细报告**：生成 DOCX 格式的审核报告，包含评分和改进建议
- ✅ **高性能**：优化的 Pipeline 设计，120 秒内完成审核
- ✅ **生产就绪**：异步处理、错误处理、日志记录完备

## 系统架构

```
文档输入 (PDF/DOCX/DOC)
    ↓
文档处理 (PyMuPDF/python-docx)
    ↓
VLM 推理 (Qwen-2.5-VL 7B)
    ↓
批注生成 (PyMuPDF)
    ↓
报告生成 (python-docx)
    ↓
输出 (带批注PDF + 审核报告)
```

## 快速开始

### 1. 环境要求

- Python 3.8+
- NVIDIA GPU (推荐 A100/A10G，最低 T4)
- vLLM 部署的 Qwen-2.5-VL 7B 模型
- LibreOffice (可选，用于 DOC/DOCX 转 PDF)

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

编辑 `config/config.yaml`，配置 vLLM 服务地址：

```yaml
vllm:
  base_url: "http://localhost:8000/v1"
  api_key: "your-api-key"
  model: "Qwen/Qwen2.5-VL-7B-Instruct"
```

### 4. 运行审核

#### 命令行方式

```bash
# 审核作业指导书
python main.py document.pdf --scenario work_instruction_audit

# 审核风险管控方案
python main.py risk_plan.docx --scenario risk_management_audit

# 指定输出名称
python main.py document.pdf --scenario work_instruction_audit --output my_audit
```

#### Python 代码方式

```python
from src.pipeline import DocumentAuditPipeline

# 创建 Pipeline
pipeline = DocumentAuditPipeline()

# 执行审核
report = pipeline.run_sync(
    document_path="document.pdf",
    scenario_id="work_instruction_audit"
)

# 查看结果
print(f"最终得分: {report.audit_result.final_score}/100")
print(f"审核结果: {'通过' if report.audit_result.passed else '不通过'}")
print(f"发现问题: {len(report.audit_result.violations)} 个")
```

## 审核场景

### 1. 作业指导书审核 (`work_instruction_audit`)

评估维度：
- **结构完整性** (20%)：目录、章节编号
- **内容完整性** (40%)：安全注意事项、操作步骤
- **格式规范性** (15%)：文本格式、标题层级
- **图表质量** (15%)：图片清晰度、表格完整性
- **附件完整性** (10%)：附录、参考文献

### 2. 风险管控方案审核 (`risk_management_audit`)

评估维度：
- **风险识别完整性** (30%)：危险源识别、风险等级评定
- **管控措施有效性** (35%)：技术措施、管理措施
- **应急预案完备性** (20%)：应急流程、联系方式
- **责任分工明确性** (10%)：岗位职责
- **检查与更新机制** (5%)：定期检查要求

## 项目结构

```
doc-anlysis/
├── src/
│   ├── core/
│   │   ├── document_processor.py    # 文档处理
│   │   ├── vlm_client.py            # VLM 推理客户端
│   │   ├── annotator.py             # 批注生成器
│   │   └── report_generator.py      # 报告生成器
│   ├── models/
│   │   ├── schemas.py               # Pydantic 数据模型
│   │   └── rule_engine.py           # 规则引擎
│   ├── utils/
│   │   ├── config.py                # 配置管理
│   │   └── logger.py                # 日志工具
│   └── pipeline.py                  # 主 Pipeline
├── config/
│   ├── audit_rules.yaml             # 审核规则
│   └── config.yaml                  # 系统配置
├── examples/
│   └── example_usage.py             # 使用示例
├── temp/                            # 临时文件
├── output/                          # 输出文件
├── logs/                            # 日志文件
├── requirements.txt                 # 依赖包
├── main.py                          # CLI 入口
└── README.md
```

## 配置说明

### 系统配置 (`config/config.yaml`)

```yaml
vllm:
  base_url: "http://localhost:8000/v1"  # vLLM 服务地址
  api_key: "token-abc123"               # API 密钥
  model: "Qwen/Qwen2.5-VL-7B-Instruct"  # 模型名称
  temperature: 0.1                      # 温度参数
  max_tokens: 3000                      # 最大 token 数

pipeline:
  timeout: 120      # 总超时时间（秒）
  dpi: 150          # 图片 DPI
  max_retries: 3    # 最大重试次数
  max_pages: 20     # 单次处理最大页数

output:
  format: "pdf"           # 输出格式
  temp_dir: "./temp"      # 临时文件目录
  output_dir: "./output"  # 输出目录
```

### 审核规则 (`config/audit_rules.yaml`)

审核规则采用 4 层架构：

```yaml
audit_scenarios:          # 审核场景
  - scenario_id: "..."
    dimensions:           # 审核维度
      - dimension_id: "..."
        items:            # 审核项
          - item_id: "..."
            checkpoints:  # 检查点
              - checkpoint_id: "..."
                description: "..."
                severity: "critical"  # critical/high/medium/low
                max_deduction: 10
```

## 输出说明

每次审核会生成两个文件：

1. **带批注的 PDF 文档** (`{name}_annotated.pdf`)
   - 高亮标注问题位置
   - 便签批注显示详细信息
   - 颜色区分严重程度（红/橙/黄/绿）

2. **审核报告** (`{name}_report.docx`)
   - 基本信息和元数据
   - 审核摘要和评分
   - 详细问题列表
   - 改进建议

## 性能优化

系统采用多项优化措施确保在 120 秒内完成：

- **文档处理**：PyMuPDF 高性能解析（0.12秒/页）
- **VLM 推理**：低温度、token 限制、批处理
- **异步处理**：CPU 密集任务并行化
- **智能降级**：超时和错误的降级策略

## 常见问题

### Q: 如何安装 LibreOffice？

**macOS**: `brew install --cask libreoffice`
**Ubuntu**: `sudo apt-get install libreoffice`
**Windows**: 从 [官网](https://www.libreoffice.org/) 下载安装

### Q: vLLM 服务如何部署？

```bash
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --max-num-batched-tokens 16384 \
  --enable-chunked-prefill \
  --gpu-memory-utilization 0.95
```

### Q: 如何自定义审核规则？

编辑 `config/audit_rules.yaml`，添加新的检查点或修改现有规则。

### Q: 处理超时怎么办？

- 减少 `max_pages` 限制
- 降低 `max_tokens` 参数
- 优化 vLLM 配置

## 技术栈

- **文档处理**: PyMuPDF, python-docx
- **VLM 模型**: Qwen-2.5-VL 7B
- **推理引擎**: vLLM
- **数据验证**: Pydantic
- **异步处理**: asyncio
- **配置管理**: PyYAML

## 许可证

本项目使用的核心依赖库许可证：

- PyMuPDF: AGPL-3.0 (商业使用需购买许可)
- python-docx: MIT
- Qwen-2.5-VL: Apache 2.0
- vLLM: Apache 2.0

## 贡献

欢迎提交 Issue 和 Pull Request！

## 技术支持

详细技术文档请参考 `指南.md`。

---

**版本**: 1.0.0  
**更新日期**: 2025年10月
