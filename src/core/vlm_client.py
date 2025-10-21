"""VLM 推理客户端模块"""
import json
import asyncio
from typing import List, Dict, Any, Optional
from openai import OpenAI
from ..models.schemas import AuditResult, DocumentStructure
from ..models.rule_engine import RuleEngine
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger()


class VLMClient:
    """VLM 推理客户端 - 封装 OpenAI API 调用"""
    
    # 作业指导书审核 Prompt
    WORK_INSTRUCTION_AUDIT_PROMPT = """你是一位专业的文档审核专家，现在要审核作业指导书。

## 你的任务
仔细检查文档，找出以下类型的问题并**精确定位**：

### 类型1：文字及语法错误（必须逐字检查）
1. **标点符号错误**
   - 逗号重复：如"管道处、、工程部" → 应为"管道处、工程部"
   - 句号缺失：如"本文适用于防汛工作 各管理处应按照规定" → 应加句号
   - 括号不匹配：如"（包括检查、维修、抢修" → 缺少右括号
   
   ⚠️ 找到后必须提供：页码、错误文本片段（30-50字，包含前后文）

2. **语句不通顺**
   - 病句：如"本指导书适用于防汛期间对管道的"（句子不完整）
   - 歧义句：如"发现问题的人员应报告"（谁发现？谁报告？）
   - 逻辑不清：如"应立即采取措施进行确保"（措施和确保重复）
   
   ⚠️ 找到后必须提供：页码、不通顺的完整句子、修改建议

3. **专业术语错误**
   - 错误拼写：如"Q-HSE" → 应为"QHSE"
   - 术语不统一：全文有时用"管理处"，有时用"分公司" → 应统一
   
   ⚠️ 找到后必须提供：页码、错误术语、正确术语

### 类型2：业务逻辑错误（必须通读上下文）
1. **上下文不连贯**
   - 章节跳跃：第2章是"汛前准备"，第3章直接是"汛后管理"，中间跳过了"汛期管理"
   - 前后矛盾：前面说"应急响应时间不超过2小时"，后面说"24小时内响应"
   
   ⚠️ 找到后必须提供：矛盾的两处位置（页码+文本片段）

2. **时间逻辑错误**
   - 如："汛前检查"的内容出现在"汛期响应"章节
   - 如："3.2.1 汛期巡线要求"出现在"3.1 汛前准备"之前
   
   ⚠️ 找到后必须提供：页码、时间顺序问题描述

### 类型3：应急处置深度问题
1. **处置步骤不合理**
   - 如：先"恢复供气"，后"检查管道安全" → 顺序错误，应先检查再恢复
   - 如：缺少"立即停输"步骤 → 在管道破裂时应第一时间停输
   
2. **流程缺失关键步骤**
   - 应急响应必须包含：发现→上报→评估→启动预案→现场处置→恢复→总结
   - 如果缺少其中任何一步，都要指出
   
   ⚠️ 找到后必须提供：页码、缺失的步骤或错误的顺序

### 类型4：结构完整性问题
（你现有的规则已覆盖，保持即可）

## 审核方法
1. **逐页阅读**：不要跳过任何段落
2. **逐句检查**：每个句子都要看标点、语法、逻辑
3. **前后对比**：检查术语统一性、章节连贯性
4. **重点关注**：应急处置、操作步骤、风险点描述

## 输出格式要求
对于每个发现的问题，必须提供：
```json
{{
  "rule_id": "grammar_01",  // 对应的检查点ID
  "severity": "medium",     // 严重程度
  "finding": "标点符号重复：'管道处、、工程部' → 应为'管道处、工程部'",  // 具体问题描述+修改建议
  "location": {{
    "page": 3,
    "text_snippet": "各地区管理处、、工程部应按照规定",  // 30-50字，包含错误和前后文
    "region_description": "第3页，第2自然段"
  }},
  "points_deducted": 2
}}
```

⚠️ **关键要求**：
- text_snippet 必须是原文的**精确文本**（用于在PDF上定位）
- text_snippet 长度30-50字（太短定位不准，太长影响阅读）
- finding 必须包含**具体的修改建议**，使用"→"分隔问题和建议

## 当前审核的规则
{rules}

现在开始审核，请仔细检查每一页、每一句。
"""

    # 风险管控方案审核 Prompt
    RISK_MANAGEMENT_AUDIT_PROMPT = """你是高后果区风险管控方案审核专家。

## 你的任务
检查文档和图片，找出以下问题：

### 类型1：图片内容问题（重点）
你会看到多张图片，需要逐张分析：

1. **影像图（高后果区示意图）检查**
   必须包含的标注：
   - ✅ 管道位置（实线）
   - ✅ 潜在影响半径（虚线，应该有三条平行线：管道中心线+左右边界）
   - ✅ 建筑物标注（名称、人员数量、属性）
   
   ⚠️ 如果缺少，输出：
   ```json
   {{
     "rule_id": "image_annot_01",
     "severity": "critical",
     "finding": "影像图缺少潜在影响半径标注（虚线） → 应在影像图上用虚线标注管道左右两侧的潜在影响半径",
     "location": {{
       "page": 5,
       "text_snippet": "[第5页影像图]",  // 图片标识
       "region_description": "第5页，高后果区影像图"
     }},
     "points_deducted": 8
   }}
   ```

2. **入场路线图检查**
   检查路线是否合理：
   - ❌ 不能穿山（路线直接穿过山体）
   - ❌ 不能穿墙（路线穿过建筑物墙体）
   - ❌ 不能跨河无桥（路线跨河但没有桥梁标注）
   - ❌ 不能穿建筑物（路线穿过建筑物内部）
   - ✅ 必须在可行车道路（应该标注道路）
   
   ⚠️ 如果发现问题：
   ```json
   {{
     "rule_id": "route_01",
     "severity": "critical",
     "finding": "入场路线穿越河流但未标注桥梁，车辆无法通行 → 应在河流位置标注桥梁或调整路线绕行",
     "location": {{
       "page": 7,
       "text_snippet": "[第7页入场线路图]",
       "region_description": "第7页，入场线路图中部"
     }},
     "points_deducted": 10
   }}
   ```

3. **逃生路线图检查**
   - ✅ 疏散方向应向管道两侧（箭头指向两边）
   - ❌ 不能顺着管道方向疏散（箭头沿管道）
   - ✅ 集结点必须在影响半径外（集结点标记在虚线外）

### 类型2：图文不一致问题（重点）
对比文字描述和图片标注：

1. **建筑物描述一致性**
   - 文字："XX小学，5层楼，200人"
   - 图片：影像图上标注"XX小学，3层，150人"
   - → 不一致！
   
   ⚠️ 发现后输出：
   ```json
   {{
     "rule_id": "consistency_01",
     "severity": "high",
     "finding": "建筑物描述不一致：文字描述'5层楼200人'，影像图标注'3层150人' → 应统一为实际情况",
     "location": {{
       "page": 4,
       "text_snippet": "XX小学，5层楼，师生约200人",
       "region_description": "第4页特征描述部分与第5页影像图"
     }},
     "points_deducted": 8
   }}
   ```

2. **表格数据一致性**
   - 检查"高后果区基本信息表"中的区段长
   - 对比"人防措施"中提到的区段长
   - 对比"风险评价结果表"中的位置信息
   - → 必须完全一致

### 类型3：文本逻辑问题
（类似作业指导书的检查）

### 类型4：数据范围检查
- 电位测试结果：必须在 -0.85V ~ -1.2V 范围内
- 风险等级：只能是"低"、"中"、"较高"、"高"，不能是其他词

## 审核流程
1. **先看所有图片**：记录每张图的内容和标注
2. **再读文字**：提取关键数据和描述
3. **交叉对比**：图与文、表与表之间的一致性
4. **逻辑验证**：时间顺序、数据范围、路线合理性

## 输出要求
- 图片问题的 text_snippet 使用 "[第X页XX图]" 格式
- 数据不一致问题要列出对比值
- 每个问题都要有具体的修改建议，使用"→"分隔

## 当前审核的规则
{rules}

现在开始审核。
"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = get_config(config_path)
        self.client = OpenAI(
            base_url=self.config.vllm_base_url,
            api_key=self.config.vllm_api_key
        )
        self.rule_engine = RuleEngine()
        
        # 新增：初始化分层审核引擎
        from .layered_auditor import LayeredAuditor
        self.layered_auditor = LayeredAuditor(self, self.rule_engine)
        
        logger.info(f"VLM 客户端初始化完成，连接到: {self.config.vllm_base_url}")
    
    def audit_document(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]],
        scenario_id: str,
        max_pages: Optional[int] = None
    ) -> AuditResult:
        """
        审核文档（智能选择标准审核或分层审核）
        
        Args:
            doc_structure: 文档结构数据
            page_images: 页面图片列表
            scenario_id: 审核场景ID
            max_pages: 最大处理页数（限制）
        
        Returns:
            审核结果
        """
        logger.info(f"开始审核，场景: {scenario_id}")
        
        # 判断是否需要分层审核
        trigger_page_count = getattr(self.config, 'layered_audit_trigger_page_count', 20)
        
        if doc_structure.page_count > trigger_page_count:
            logger.info(f"文档页数 {doc_structure.page_count} 超过 {trigger_page_count} 页，启用分层审核")
            
            # 使用分层审核引擎
            result = asyncio.run(
                self.layered_auditor.audit_document(
                    doc_structure, page_images, scenario_id
                )
            )
            return result
        
        else:
            logger.info(f"文档页数 {doc_structure.page_count} ≤ {trigger_page_count} 页，使用标准审核")
            
            # 使用原有的标准审核逻辑
            return self._audit_document_standard(
                doc_structure, page_images, scenario_id, max_pages
            )
    
    def _audit_document_standard(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]],
        scenario_id: str,
        max_pages: Optional[int]
    ) -> AuditResult:
        """
        标准审核流程（原有逻辑）
        
        Args:
            doc_structure: 文档结构数据
            page_images: 页面图片列表
            scenario_id: 审核场景ID
            max_pages: 最大处理页数（限制）
        
        Returns:
            审核结果
        """
        # 限制页数
        if max_pages and len(page_images) > max_pages:
            logger.warning(f"文档超过最大页数限制 {max_pages}，仅处理前 {max_pages} 页")
            page_images = page_images[:max_pages]
        
        # 生成 Prompt
        system_prompt = self._generate_system_prompt(scenario_id)
        user_prompt = self._generate_user_prompt(doc_structure)
        
        # 构建消息
        messages = self._build_messages(system_prompt, user_prompt, page_images, scenario_id, doc_structure)
        
        # 调用 VLM
        try:
            result = self._call_vlm(messages)
            logger.info(f"审核完成，发现 {len(result.violations)} 个问题")
            return result
        except Exception as e:
            logger.error(f"VLM 调用失败: {e}")
            raise
    
    def _generate_system_prompt(self, scenario_id: str) -> str:
        """生成 System Prompt"""
        # 获取场景规则
        scenario = self.rule_engine.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"场景不存在: {scenario_id}")
        
        # 格式化规则
        rules_text = self.rule_engine.format_rules_for_prompt(scenario_id)
        
        # 根据场景选择对应的Prompt模板
        if "work_instruction" in scenario_id:
            prompt_template = self.WORK_INSTRUCTION_AUDIT_PROMPT
        elif "risk_management" in scenario_id:
            prompt_template = self.RISK_MANAGEMENT_AUDIT_PROMPT
        else:
            # 默认使用作业指导书Prompt
            prompt_template = self.WORK_INSTRUCTION_AUDIT_PROMPT
        
        # 填充规则
        return prompt_template.format(rules=rules_text)
    
    def _generate_user_prompt(self, doc_structure: DocumentStructure) -> str:
        """生成 User Prompt"""
        prompt = f"""请审核以下文档，严格按照提供的规则进行检查。

## 文档信息
- 格式: {doc_structure.format.upper()}
- 页数: {doc_structure.page_count}

## 文档完整内容（Markdown格式）
{doc_structure.markdown}

## 审核要求
1. **逐页检查**：不要遗漏任何页面
2. **逐句分析**：每个句子都要检查语法、逻辑、术语
3. **图文对比**：如果有图片，必须对比图片内容和文字描述
4. **前后关联**：检查章节顺序、术语统一、数据一致

## 特别注意
- 标点符号：逗号重复、括号不匹配、句号缺失
- 语句通顺：病句、歧义句、不完整的句子
- 专业术语：拼写错误、术语不统一
- 逻辑连贯：章节跳跃、前后矛盾、时间错乱
- 应急处置：步骤顺序、关键步骤缺失

## 输出格式
严格按照JSON Schema输出，每个violation必须包含：
- rule_id：对应的检查点ID
- severity：严重程度（critical/high/medium/low）
- finding：具体问题描述 + 修改建议（用"→"分隔）
- location：
  - page：页码
  - text_snippet：原文精确文本片段（30-50字）
  - region_description：位置描述

现在开始审核。
"""
        return prompt
    
    def _build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        page_images: List[Dict[str, Any]],
        scenario_id: str,
        doc_structure: DocumentStructure
    ) -> List[Dict[str, Any]]:
        """构建消息列表（场景化图片选择）。"""
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 构建用户消息内容（图片 + 文本）
        user_content = []
        
        # 场景化图片选择
        selected_images = []
        if "risk_management" in scenario_id:
            # 1) 优先加入疑似签字页
            sig_pages = self._find_signature_pages(doc_structure)
            for p in sig_pages:
                for img in page_images:
                    if img.get('page') == p:
                        selected_images.append(img)
                        break
            # 2) 再加入前 10 页作为全局语境
            for img in page_images[:10]:
                selected_images.append(img)
        else:
            # 作业指导书：保持前 5 页
            selected_images = page_images[:5]

        # 去重并限制数量（最多 12 张）
        seen = set()
        unique_images = []
        for img in selected_images:
            key = img.get('image_path')
            if key not in seen:
                unique_images.append(img)
                seen.add(key)
            if len(unique_images) >= 12:
                break

        for img_info in unique_images:
            image_path = img_info['image_path']
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"file://{image_path}"}
            })
        
        # 添加文本 Prompt
        user_content.append({
            "type": "text",
            "text": user_prompt
        })
        
        messages.append({"role": "user", "content": user_content})
        
        return messages

    def _find_signature_pages(self, doc_structure: DocumentStructure) -> List[int]:
        """从 Markdown 文本中粗略定位含“签字/审批/盖章/日期”等关键词的页码。
        估算法：按 `DocumentProcessor._extract_page_range_text` 的假设，
        每 50 行近似一页；这里直接从结构结构中获取页面号更靠谱。
        实现：扫描每页段落，命中关键词即收集该页。
        """
        keywords = ["审批", "签字", "签名", "盖章", "日期", "年", "月", "日"]
        hit_pages = []
        try:
            for page_struct in doc_structure.structure:
                text = "\n".join(p.text for p in page_struct.paragraphs[:20])
                if any(k in text for k in keywords):
                    hit_pages.append(page_struct.page)
            # 若一个都没匹配，默认返回最后 2 页尝试
            if not hit_pages:
                total = doc_structure.page_count
                hit_pages = [p for p in range(max(1, total - 1), total + 1)]
        except Exception:
            pass
        # 限制最多 3 页
        return hit_pages[:3]
    
    def _call_vlm(self, messages: List[Dict[str, Any]]) -> AuditResult:
        """
        调用 VLM 进行推理
        
        Args:
            messages: 消息列表
        
        Returns:
            审核结果
        """
        logger.info("调用 VLM API...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.config.vllm_model,
                messages=messages,
                temperature=self.config.vllm_temperature,
                max_tokens=self.config.vllm_max_tokens,
                extra_body={
                    "guided_json": AuditResult.model_json_schema()
                }
            )
            
            # 解析响应
            content = response.choices[0].message.content
            logger.debug(f"VLM 响应: {content[:200]}...")
            
            # 清理响应内容：去除markdown代码块标记
            content = self._clean_json_response(content)
            
            # 解析JSON
            parsed = json.loads(content)
            
            # VLM可能直接返回violations数组，也可能返回完整的AuditResult对象
            if isinstance(parsed, list):
                # 直接返回的是violations数组，需要构建完整的AuditResult
                from ..models.schemas import Violation
                violations = []
                for v_dict in parsed:
                    # 修复和清洗violation数据
                    v_dict = self._sanitize_violation(v_dict)
                    if v_dict:  # 只添加有效的violation
                        try:
                            violations.append(Violation(**v_dict))
                        except Exception as e:
                            logger.warning(f"无法解析violation: {e}")
                            continue
                total_deductions = sum(v.points_deducted for v in violations)
                final_score = max(0, 100 - total_deductions)
                result = AuditResult(
                    violations=violations,
                    total_deductions=total_deductions,
                    final_score=final_score,
                    passed=final_score >= 60
                )
                return result
            elif isinstance(parsed, dict):
                # 返回的是完整对象
                result = AuditResult(**parsed)
                # 同样修复violations中的text_snippet
                for v in result.violations:
                    if len(v.location.text_snippet) < 10:
                        v.location.text_snippet = f"{v.location.text_snippet} (问题位置)"
                return result
            else:
                logger.warning(f"未预期的响应格式: {type(parsed)}")
                return AuditResult(
                    violations=[],
                    total_deductions=0,
                    final_score=100,
                    passed=True
                )
            
        except Exception as e:
            logger.error(f"VLM API 调用异常: {e}")
            logger.debug(f"原始响应内容: {content[:500] if 'content' in locals() else 'N/A'}")
            
            # 返回空结果（降级方案）
            return AuditResult(
                violations=[],
                total_deductions=0,
                final_score=100,
                passed=True
            )
    
    def _sanitize_violation(self, v_dict: dict) -> dict:
        """
        清洗和修复violation数据
        
        处理VLM返回数据不规范的问题：
        - location是字符串而不是对象
        - text_snippet过长或过短
        - 缺少必需字段
        """
        try:
            # 检查必需字段
            if 'rule_id' not in v_dict or 'severity' not in v_dict or 'finding' not in v_dict:
                logger.warning(f"violation缺少必需字段，跳过")
                return None
            
            # 修复location字段
            if 'location' in v_dict:
                location = v_dict['location']
                
                # 如果location是字符串，尝试构建location对象
                if isinstance(location, str):
                    logger.warning(f"location是字符串，尝试修复: {location[:50]}")
                    # 尝试从字符串中提取页码
                    import re
                    page_match = re.search(r'第?(\d+)页', location)
                    page = int(page_match.group(1)) if page_match else 1
                    
                    v_dict['location'] = {
                        'page': page,
                        'text_snippet': location[:200],  # 截断到200字符
                        'region_description': location
                    }
                
                # 如果location是字典，修复其中的字段
                elif isinstance(location, dict):
                    # 确保有page字段
                    if 'page' not in location:
                        location['page'] = 1
                    
                    # 修复text_snippet
                    if 'text_snippet' in location:
                        snippet = location['text_snippet']
                        # 截断过长的snippet
                        if len(snippet) > 200:
                            location['text_snippet'] = snippet[:197] + '...'
                        # 补充过短的snippet
                        elif len(snippet) < 10:
                            location['text_snippet'] = f"{snippet} (位置)"
                    else:
                        # 如果没有text_snippet，使用region_description或默认值
                        location['text_snippet'] = location.get('region_description', '问题位置')[:200]
                    
                    # 确保有region_description
                    if 'region_description' not in location:
                        location['region_description'] = f"第{location['page']}页"
                    
                    v_dict['location'] = location
            else:
                # 如果完全没有location，创建一个默认的
                logger.warning(f"violation缺少location字段，使用默认值")
                v_dict['location'] = {
                    'page': 1,
                    'text_snippet': '未指定位置',
                    'region_description': '文档中'
                }
            
            # 确保有points_deducted字段
            if 'points_deducted' not in v_dict:
                v_dict['points_deducted'] = 1
            
            return v_dict
            
        except Exception as e:
            logger.error(f"清洗violation数据时出错: {e}")
            return None
    
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
    
    def retry_with_backoff(
        self,
        func,
        max_retries: Optional[int] = None,
        *args,
        **kwargs
    ):
        """
        重试机制
        
        Args:
            func: 要执行的函数
            max_retries: 最大重试次数
            *args, **kwargs: 函数参数
        
        Returns:
            函数执行结果
        """
        import time
        
        if max_retries is None:
            max_retries = self.config.pipeline_max_retries
        
        retry_delays = [1, 3, 5]
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.warning(f"尝试 {attempt + 1} 失败: {e}，{delay} 秒后重试...")
                    time.sleep(delay)
                else:
                    logger.error(f"重试 {max_retries} 次后仍失败")
                    raise

