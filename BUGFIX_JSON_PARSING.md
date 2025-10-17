# Bug修复：VLM返回JSON格式问题

## 问题描述

VLM返回的JSON存在两个问题：

1. **被包裹在markdown代码块中**（如 ` ```json\n{...}\n``` `）
2. **返回格式不一致**：有时返回violations数组`[{...}]`，有时返回完整对象`{"violations": [...], ...}`

错误信息：
```
# 问题1: markdown代码块
Invalid JSON: expected value at line 1 column 1
input_value='```json\n[...]\n```'

# 问题2: 格式不匹配
Input should be an object [type=model_type, input_value=[{...}], input_type=list]
```

## 解决方案

在两个文件中：
1. 添加JSON响应清理函数，去除markdown代码块标记
2. 兼容处理两种返回格式（数组或完整对象）

## 需要修改的文件

### 1. `src/core/layered_auditor.py`

在 `_call_vlm_simple` 方法中，在解析JSON前添加清理步骤：

**修改位置：** 约第482-489行

**原代码：**
```python
content = response.choices[0].message.content
result = AuditResult.model_validate_json(content)
return result.violations
```

**修改为：**
```python
content = response.choices[0].message.content

# 清理响应内容：去除markdown代码块标记
content = self._clean_json_response(content)

result = AuditResult.model_validate_json(content)
return result.violations
```

**并在类中添加新方法：**（约第496行后）
```python
def _clean_json_response(self, content: str) -> str:
    """
    清理VLM响应内容，去除markdown代码块标记
    
    处理以下情况：
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - {..}
    """
    content = content.strip()
    
    # 去除开头的```json或```
    if content.startswith('```json'):
        content = content[7:].strip()
    elif content.startswith('```'):
        content = content[3:].strip()
    
    # 去除结尾的```
    if content.endswith('```'):
        content = content[:-3].strip()
    
    return content
```

### 2. `src/core/vlm_client.py`

在 `_call_vlm` 方法中做同样的修改：

**修改位置：** 约第430-438行

**原代码：**
```python
# 解析响应
content = response.choices[0].message.content
logger.debug(f"VLM 响应: {content[:200]}...")

# 验证并解析 JSON
result = AuditResult.model_validate_json(content)
```

**修改为：**
```python
# 解析响应
content = response.choices[0].message.content
logger.debug(f"VLM 响应: {content[:200]}...")

# 清理响应内容：去除markdown代码块标记
content = self._clean_json_response(content)

# 验证并解析 JSON
result = AuditResult.model_validate_json(content)
```

**并在类中添加新方法：**（约第453行后）
```python
def _clean_json_response(self, content: str) -> str:
    """
    清理VLM响应内容，去除markdown代码块标记
    
    处理以下情况：
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - {...}
    """
    content = content.strip()
    
    # 去除开头的```json或```
    if content.startswith('```json'):
        content = content[7:].strip()
    elif content.startswith('```'):
        content = content[3:].strip()
    
    # 去除结尾的```
    if content.endswith('```'):
        content = content[:-3].strip()
    
    return content
```

## 验证修复

修复后，再次运行应该看到：
- ✓ VLM调用成功
- ✓ 能够正确解析violations
- ✓ 分层审核正常进行

## 快速应用（如果已推送到服务器）

在服务器上执行：
```bash
cd /path/to/doc-anlysis
git pull
# 或者直接手动修改上述两个文件
```

然后重新运行审核：
```bash
python main.py your_document.pdf --scenario work_instruction_audit
```

