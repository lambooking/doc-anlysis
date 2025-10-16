# 使用指南

## 系统配置

### 1. 配置 vLLM 服务

编辑 `config/config.yaml`：

```yaml
vllm:
  base_url: "http://localhost:8000/v1"  # 修改为您的 vLLM 服务地址
  api_key: "your-api-key"                # 修改为您的 API 密钥
  model: "Qwen/Qwen2.5-VL-7B-Instruct"
```

### 2. 调整性能参数

```yaml
pipeline:
  timeout: 120      # 总超时时间（秒）
  dpi: 150          # 图片 DPI（越高越清晰但越慢）
  max_retries: 3    # 失败重试次数
  max_pages: 20     # 单次处理最大页数（超过会截断）
```

### 3. 配置输出路径

```yaml
output:
  temp_dir: "./temp"      # 临时文件目录
  output_dir: "./output"  # 输出文件目录
```

## 基本使用

### 命令行方式

```bash
# 基本用法
python main.py <文档路径> --scenario <场景ID>

# 示例
python main.py document.pdf --scenario work_instruction_audit
python main.py plan.docx --scenario risk_management_audit

# 指定输出名称
python main.py document.pdf --scenario work_instruction_audit --output my_audit
```

### Python 代码方式

```python
from src.pipeline import DocumentAuditPipeline

# 创建 Pipeline
pipeline = DocumentAuditPipeline()

# 执行审核
report = pipeline.run_sync(
    document_path="document.pdf",
    scenario_id="work_instruction_audit"
)

# 访问结果
print(f"得分: {report.audit_result.final_score}/100")
print(f"通过: {report.audit_result.passed}")
print(f"问题数: {len(report.audit_result.violations)}")

# 访问输出文件
print(f"批注文档: {report.annotated_document_path}")
print(f"审核报告: {report.report_path}")
```

## 审核场景

### 1. 作业指导书审核

```bash
python main.py work_instruction.pdf --scenario work_instruction_audit
```

**评估内容**：
- 结构完整性（20%）
- 内容完整性（40%）
- 格式规范性（15%）
- 图表质量（15%）
- 附件完整性（10%）

### 2. 风险管控方案审核

```bash
python main.py risk_plan.docx --scenario risk_management_audit
```

**评估内容**：
- 风险识别完整性（30%）
- 管控措施有效性（35%）
- 应急预案完备性（20%）
- 责任分工明确性（10%）
- 检查与更新机制（5%）

## 高级用法

### 异步批量处理

```python
import asyncio
from src.pipeline import DocumentAuditPipeline

async def batch_audit():
    pipeline = DocumentAuditPipeline()
    
    # 定义任务
    tasks = [
        pipeline.process_document("doc1.pdf", "work_instruction_audit"),
        pipeline.process_document("doc2.pdf", "work_instruction_audit"),
        pipeline.process_document("doc3.docx", "risk_management_audit"),
    ]
    
    # 并发执行
    reports = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    for i, report in enumerate(reports):
        if isinstance(report, Exception):
            print(f"文档 {i+1} 失败: {report}")
        else:
            print(f"文档 {i+1} 得分: {report.audit_result.final_score}/100")

# 运行
asyncio.run(batch_audit())
```

### 自定义规则

编辑 `config/audit_rules.yaml` 添加或修改规则：

```yaml
audit_scenarios:
  - scenario_id: "my_custom_audit"
    name: "自定义审核"
    total_points: 100
    
    dimensions:
      - dimension_id: "my_dimension"
        name: "我的维度"
        weight: 1.0
        
        items:
          - item_id: "my_item"
            name: "我的审核项"
            
            checkpoints:
              - checkpoint_id: "check_01"
                description: "检查某个内容"
                severity: "critical"
                max_deduction: 10
```

然后使用：

```python
report = pipeline.run_sync(
    document_path="document.pdf",
    scenario_id="my_custom_audit"
)
```

### 错误处理

```python
import asyncio
from src.pipeline import DocumentAuditPipeline

pipeline = DocumentAuditPipeline()

try:
    report = pipeline.run_sync(
        document_path="document.pdf",
        scenario_id="work_instruction_audit"
    )
    print("审核成功！")
    
except FileNotFoundError:
    print("文件不存在")
    
except ValueError as e:
    print(f"参数错误: {e}")
    
except asyncio.TimeoutError:
    print("处理超时（超过 120 秒）")
    print("建议：减少文档页数或调整 max_pages 参数")
    
except Exception as e:
    print(f"审核失败: {e}")
```

## 输出文件说明

### 带批注的 PDF 文档

文件名：`{输出名称}_annotated.pdf`

**特性**：
- 高亮标注问题位置
- 颜色区分严重程度：
  - 🔴 红色：关键问题（critical）
  - 🟠 橙色：高优先级（high）
  - 🟡 黄色：中优先级（medium）
  - 🟢 绿色：低优先级（low）
- 便签批注显示详细信息
- 可在 PDF 阅读器中查看和编辑

### 审核报告文档

文件名：`{输出名称}_report.docx`

**内容结构**：
1. 基本信息（文档名、日期、审核人）
2. 审核摘要（问题统计）
3. 评分结果（得分和通过状态）
4. 详细问题列表（按严重程度分组）
5. 改进建议

## 性能优化建议

### 处理大文档

如果文档超过 20 页：

```yaml
# config/config.yaml
pipeline:
  max_pages: 10  # 减少处理页数
  timeout: 90    # 减少超时时间
```

或使用分段处理：

```python
# 仅处理前 10 页
pipeline.config.pipeline_max_pages = 10
report = pipeline.run_sync(document_path, scenario_id)
```

### 提升速度

1. **降低图片 DPI**：
```yaml
pipeline:
  dpi: 100  # 默认 150
```

2. **减少 token 数量**：
```yaml
vllm:
  max_tokens: 1500  # 默认 3000
```

3. **提高温度（牺牲准确性）**：
```yaml
vllm:
  temperature: 0.3  # 默认 0.1
```

### 提升准确性

1. **增加图片质量**：
```yaml
pipeline:
  dpi: 200  # 默认 150
```

2. **增加 token 数量**：
```yaml
vllm:
  max_tokens: 4000  # 默认 3000
```

3. **降低温度**：
```yaml
vllm:
  temperature: 0.05  # 默认 0.1
```

## 常见问题

### Q: 提示 LibreOffice 未安装

**A**: 安装 LibreOffice：
- macOS: `brew install --cask libreoffice`
- Ubuntu: `sudo apt-get install libreoffice`
- Windows: 从官网下载安装

### Q: VLM API 连接失败

**A**: 检查配置：
1. 确认 vLLM 服务正在运行
2. 检查 `base_url` 是否正确
3. 检查网络连接
4. 查看 vLLM 日志

### Q: 处理超时

**A**: 优化参数：
1. 减少 `max_pages`
2. 降低 `dpi`
3. 减少 `max_tokens`
4. 增加 `timeout`

### Q: 批注定位不准确

**A**: 
1. 提高 `dpi` 参数
2. 确保文档是可搜索的 PDF（非扫描件）
3. 检查文档格式是否规范

### Q: 如何查看日志

**A**: 日志文件位于 `logs/audit.log`：

```bash
tail -f logs/audit.log
```

或在代码中调整日志级别：

```yaml
logging:
  level: "DEBUG"  # INFO, DEBUG, WARNING, ERROR
```

## 最佳实践

1. **文档准备**：
   - 使用可搜索的 PDF（非扫描件）
   - 确保文档格式规范
   - 控制文档页数在 20 页以内

2. **配置调优**：
   - 根据硬件调整 DPI 和超时
   - 平衡速度和准确性
   - 定期检查日志

3. **结果验证**：
   - 检查批注定位是否准确
   - 对比审核报告和原文档
   - 必要时人工复核

4. **规则维护**：
   - 定期更新审核规则
   - 根据反馈优化检查点
   - 保持规则版本控制

## 技术支持

- 查看详细技术文档：`指南.md`
- 查看示例代码：`examples/example_usage.py`
- 查看项目结构：`README.md`

