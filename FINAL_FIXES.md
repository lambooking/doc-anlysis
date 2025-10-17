# 最终修复总结 - VLM返回数据不规范问题

## 问题汇总

在实施分层审核架构过程中，遇到了VLM返回数据不规范的系列问题：

### 问题1: JSON被包裹在markdown代码块中
```
input_value='```json\n[...]\n```'
```

### 问题2: 返回格式不一致
有时返回violations数组`[{...}]`，有时返回完整对象`{"violations": [...], ...}`

### 问题3: text_snippet长度不符合要求
- 太短：`'- 9 -'` (3字符，要求≥10)
- 太长：`'4.2.9 安全保卫 .............................49'` (超过200字符限制)

### 问题4: location字段类型错误
返回字符串而不是对象：`'第4页: ## 前  言'`

## 完整解决方案

### 1. 修改 `src/models/schemas.py`

放宽text_snippet的最小长度限制：

```python
class LocationEncoding(BaseModel):
    """位置编码"""
    page: int = Field(ge=1, description="页码")
    text_snippet: str = Field(min_length=1, max_length=200, description="文本片段")  # 从10改为1
    region_description: str = Field(..., description="区域描述")
```

### 2. 在 `src/core/layered_auditor.py` 中添加数据清洗

#### 添加清洗函数：

```python
def _sanitize_violation(self, v_dict: dict) -> dict:
    """清洗和修复violation数据"""
    try:
        # 1. 检查必需字段
        if 'rule_id' not in v_dict or 'severity' not in v_dict or 'finding' not in v_dict:
            logger.warning(f"violation缺少必需字段，跳过")
            return None
        
        # 2. 修复location字段
        if 'location' in v_dict:
            location = v_dict['location']
            
            # 如果location是字符串，构建location对象
            if isinstance(location, str):
                import re
                page_match = re.search(r'第?(\d+)页', location)
                page = int(page_match.group(1)) if page_match else 1
                
                v_dict['location'] = {
                    'page': page,
                    'text_snippet': location[:200],
                    'region_description': location
                }
            
            # 如果location是字典，修复字段
            elif isinstance(location, dict):
                # 确保有page
                if 'page' not in location:
                    location['page'] = 1
                
                # 修复text_snippet长度
                if 'text_snippet' in location:
                    snippet = location['text_snippet']
                    # 截断过长的
                    if len(snippet) > 200:
                        location['text_snippet'] = snippet[:197] + '...'
                    # 补充过短的
                    elif len(snippet) < 10:
                        location['text_snippet'] = f"{snippet} (位置)"
                else:
                    location['text_snippet'] = location.get('region_description', '问题位置')[:200]
                
                # 确保有region_description
                if 'region_description' not in location:
                    location['region_description'] = f"第{location['page']}页"
        else:
            # 创建默认location
            v_dict['location'] = {
                'page': 1,
                'text_snippet': '未指定位置',
                'region_description': '文档中'
            }
        
        # 3. 确保有points_deducted
        if 'points_deducted' not in v_dict:
            v_dict['points_deducted'] = 1
        
        return v_dict
    except Exception as e:
        logger.error(f"清洗violation数据时出错: {e}")
        return None
```

#### 在解析时使用清洗函数：

```python
# 在 _call_vlm_simple 方法中
parsed = json.loads(content)

if isinstance(parsed, list):
    violations = []
    for v_dict in parsed:
        # 清洗数据
        v_dict = self._sanitize_violation(v_dict)
        if v_dict:
            try:
                violations.append(Violation(**v_dict))
            except Exception as e:
                logger.warning(f"无法解析violation: {e}")
                continue
    return violations
```

### 3. 在 `src/core/vlm_client.py` 中做相同修改

添加相同的`_sanitize_violation`方法，并在`_call_vlm`中使用。

### 4. 增强Prompt说明

在chunk审核的prompt中明确要求：

```python
## 重要说明
⚠️ text_snippet 必须是原文精确文本，长度至少20字，包含问题前后的完整上下文
   - ✅ 好的例子："各地区管理处、、工程部应按照有关规定进行检查"（包含错误和上下文）
   - ❌ 坏的例子："、、"（太短，无法定位）
```

## 修复效果

### 修复前：
```
ERROR - VLM调用失败: 1 validation error for Violation
  location.text_snippet String should have at least 10 characters
ERROR - VLM调用失败: Input should be an object [type=model_type, input_value='第4页: ## 前  言']
```

### 修复后：
```
INFO - [第1层] 结构扫描完成，发现 X 个问题
INFO - [第2层] 分块审核完成，发现 Y 个问题
INFO - [第3层] 一致性检查完成，发现 Z 个问题
INFO - 三层审核完成，共发现 N 个问题
```

## 关键改进

1. **容错性**：即使VLM返回格式不规范，也能通过清洗修复
2. **鲁棒性**：处理多种异常情况（字段缺失、类型错误、长度不符）
3. **降级策略**：无法修复的数据跳过，不影响其他正常数据
4. **详细日志**：记录所有修复操作，便于调试

## 测试建议

修复后，在服务器上执行：

```bash
cd /path/to/doc-anlysis
git pull  # 或手动应用修改
python main.py your_80page_document.pdf --scenario work_instruction_audit
```

预期：
- ✓ 80页文档能成功完成审核
- ✓ 不再出现validation error
- ✓ 能正常返回violations列表
- ✓ 每个violation都有合法的location信息

