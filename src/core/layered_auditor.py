"""分层审核引擎 - 解决超长文档问题"""
import asyncio
import re
import json
from typing import List, Dict, Any, Optional
from ..models.schemas import AuditResult, Violation, DocumentStructure
from ..utils.logger import get_logger

logger = get_logger()


class LayeredAuditor:
    """三层渐进式审核引擎"""
    
    def __init__(self, vlm_client, rule_engine):
        self.vlm_client = vlm_client
        self.rule_engine = rule_engine
        
        # 从配置中读取参数
        config = vlm_client.config
        self.chunk_size = config.layered_audit_chunk_size
        self.max_tokens_per_request = config.vllm_max_tokens
        self.max_concurrent_chunks = config.layered_audit_max_concurrent_chunks
    
    async def audit_document(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]],
        scenario_id: str
    ) -> AuditResult:
        """
        三层审核主流程
        
        Returns:
            汇总的审核结果
        """
        logger.info("=" * 60)
        logger.info("开始三层渐进式审核")
        logger.info("=" * 60)
        
        all_violations = []
        
        # === 第1层：结构扫描 ===
        logger.info("\n[第1层] 结构扫描...")
        structure_violations = await self._layer1_structure_scan(
            doc_structure, scenario_id
        )
        all_violations.extend(structure_violations)
        logger.info(f"✓ 结构扫描完成，发现 {len(structure_violations)} 个问题")
        
        # === 第2层：分块深度审核 ===
        logger.info("\n[第2层] 分块深度审核...")
        content_violations = await self._layer2_chunked_audit(
            doc_structure, page_images, scenario_id
        )
        all_violations.extend(content_violations)
        logger.info(f"✓ 分块审核完成，发现 {len(content_violations)} 个问题")
        
        # === 第3层：跨文档一致性检查 ===
        logger.info("\n[第3层] 跨文档一致性检查...")
        consistency_violations = await self._layer3_consistency_check(
            doc_structure, scenario_id
        )
        all_violations.extend(consistency_violations)
        logger.info(f"✓ 一致性检查完成，发现 {len(consistency_violations)} 个问题")
        
        # 汇总结果
        logger.info("\n" + "=" * 60)
        logger.info(f"三层审核完成，共发现 {len(all_violations)} 个问题")
        logger.info("=" * 60)
        
        return self._build_audit_result(all_violations)
    
    # ========== 第1层：结构扫描 ==========
    
    async def _layer1_structure_scan(
        self,
        doc_structure: DocumentStructure,
        scenario_id: str
    ) -> List[Violation]:
        """
        第1层：快速结构扫描
        
        检查内容：
        - 目录完整性
        - 章节编号规范性
        - 必要章节是否存在
        - 表格/图片数量
        """
        logger.info("  → 提取文档结构元数据...")
        
        # 提取目录和章节结构
        toc_info = self._extract_toc(doc_structure)
        chapter_info = self._extract_chapters(doc_structure)
        
        # 构建轻量级prompt（只包含结构信息）
        structure_prompt = f"""请审核以下文档的结构完整性。

## 文档结构信息
- 总页数: {doc_structure.page_count}
- 目录: 
{toc_info}

- 章节列表:
{chapter_info}

## 审核要点
1. 目录是否涵盖必要模块（作业区概况、QHSE目标、岗位职责、作业流程等）
2. 章节编号是否规范（如1、1.1、1.1.1分级）
3. 章节顺序是否合理（如汛前→汛期→汛后）
4. 是否缺少关键章节

## 输出格式
只返回 violations 数组，不要其他字段：

{{
  "violations": [
    {{
      "rule_id": "toc_01",
      "severity": "medium",
      "finding": "具体问题描述 → 修改建议",
      "location": {{
        "page": 1,
        "text_snippet": "章节标题原文（20-50字）",
        "region_description": "第X页，目录部分"
      }},
      "points_deducted": 2
    }}
  ]
}}

⚠️ 不要包含 total_deductions, final_score, passed 等字段
"""
        
        logger.info("  → 调用VLM进行结构分析...")
        violations = await self._call_vlm_simple(structure_prompt, scenario_id)
        
        return violations
    
    def _extract_toc(self, doc_structure: DocumentStructure) -> str:
        """提取目录信息"""
        # 从markdown中提取标题行
        lines = doc_structure.markdown.split('\n')
        toc_lines = [line for line in lines if line.startswith('#') and not line.startswith('####')]
        
        if not toc_lines:
            return "（未找到明显的目录结构）"
        
        return '\n'.join(toc_lines[:50])  # 只取前50行标题
    
    def _extract_chapters(self, doc_structure: DocumentStructure) -> str:
        """提取章节列表"""
        lines = doc_structure.markdown.split('\n')
        chapters = []
        
        for i, line in enumerate(lines):
            # 匹配标题（# 或 ##）
            if line.startswith('# ') or line.startswith('## '):
                # 计算大致在第几页（简单估算：每50行约1页）
                page_num = min(i // 50 + 1, doc_structure.page_count)
                chapters.append(f"第{page_num}页: {line.strip()}")
                
                if len(chapters) >= 30:  # 最多取30个章节
                    break
        
        if not chapters:
            return "（未找到明显的章节标题）"
        
        return '\n'.join(chapters)
    
    # ========== 第2层：分块深度审核 ==========
    
    async def _layer2_chunked_audit(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]],
        scenario_id: str
    ) -> List[Violation]:
        """
        第2层：分块深度审核
        
        策略：
        1. 按3-5页为单位分块
        2. 每块独立审核（语法、逻辑、术语）
        3. 携带页码偏移信息
        """
        logger.info(f"  → 将 {doc_structure.page_count} 页文档分为多个块...")
        
        # 分块
        chunks = self._split_into_chunks(doc_structure, page_images)
        logger.info(f"  → 共分为 {len(chunks)} 个块，每块约 {self.chunk_size} 页")
        
        all_violations = []
        
        # 并发处理所有块（控制并发数）
        semaphore = asyncio.Semaphore(self.max_concurrent_chunks)
        
        tasks = []
        for i, chunk in enumerate(chunks):
            task = self._audit_single_chunk(
                chunk, i, scenario_id, semaphore
            )
            tasks.append(task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 汇总结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"  ✗ 块 {i+1} 审核失败: {result}")
            else:
                all_violations.extend(result)
                if result:
                    logger.info(f"  ✓ 块 {i+1} 完成，发现 {len(result)} 个问题")
                else:
                    logger.info(f"  ✓ 块 {i+1} 完成，未发现问题")
        
        return all_violations
    
    def _split_into_chunks(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """将文档分块"""
        chunks = []
        total_pages = doc_structure.page_count
        
        for start_page in range(1, total_pages + 1, self.chunk_size):
            end_page = min(start_page + self.chunk_size - 1, total_pages)
            
            # 提取该块的文本内容（从结构化数据中提取）
            chunk_text = self._extract_page_range_text(
                doc_structure, start_page, end_page
            )
            
            # 提取该块的图片（如果有）
            chunk_images = [
                img for img in page_images 
                if start_page <= img['page'] <= end_page
            ]
            
            chunks.append({
                'start_page': start_page,
                'end_page': end_page,
                'text': chunk_text,
                'images': chunk_images[:2]  # 每块最多2张图片
            })
        
        return chunks
    
    def _extract_page_range_text(
        self,
        doc_structure: DocumentStructure,
        start_page: int,
        end_page: int
    ) -> str:
        """提取指定页码范围的文本"""
        # 从结构化数据中提取
        page_texts = []
        
        for page_struct in doc_structure.structure:
            if start_page <= page_struct.page <= end_page:
                # 提取该页的所有段落
                page_text = f"\n--- 第 {page_struct.page} 页 ---\n"
                for para in page_struct.paragraphs:
                    page_text += para.text + "\n\n"
                page_texts.append(page_text)
        
        return '\n'.join(page_texts)
    
    async def _audit_single_chunk(
        self,
        chunk: Dict[str, Any],
        chunk_idx: int,
        scenario_id: str,
        semaphore: asyncio.Semaphore
    ) -> List[Violation]:
        """审核单个文档块"""
        async with semaphore:
            logger.info(f"    → 审核块 {chunk_idx+1}: 第{chunk['start_page']}-{chunk['end_page']}页...")
            
            # 构建针对该块的prompt（增强版）
            chunk_prompt = f"""请审核以下文档片段（第{chunk['start_page']}-{chunk['end_page']}页）。

## 审核内容
{chunk['text']}

## 审核要点
1. **语法检查**：标点符号、病句、术语拼写
2. **逻辑检查**：上下文连贯、时间顺序、前后矛盾
3. **内容检查**：操作步骤完整性、安全注意事项

## ⚠️ CRITICAL: text_snippet 要求
这是最重要的要求，必须严格遵守：

1. **必须是原文精确文本**，不是问题描述！
   ✅ 正确："各地区管理处、、工程部应按照有关规定"（原文，包含错误）
   ❌ 错误："标点符号重复"（这是问题描述）
   ❌ 错误："- 9 - (位置)"（这是页码）
   ❌ 错误："应急步骤顺序不合理"（这是评价）

2. **长度要求：至少 20 个字符，最多 150 个字符**
   - 太短：无法定位（如 "LZC 支线"）
   - 太长：影响性能

3. **必须包含错误前后的上下文**
   ✅ 正确："管理处、、工程部"（完整错误+上下文）
   ❌ 错误："、、"（只有错误，无法定位）

4. **不要包含任何标记**
   ❌ 错误："LZC 支线 (位置)"
   ❌ 错误："- 9 -"
   ❌ 错误："第4页: ## 前  言"
   ✅ 正确："LZC 支线沿线经过多个乡镇"

5. **如果是表格问题，摘录表格中的文字**
   ✅ 正确："站场名称    坐标    备注"

6. **如果是图片问题，用格式：[第X页图片]**
   ✅ 正确："[第5页影像图]"

## 输出格式
只返回 violations 数组：

{{
  "violations": [
    {{
      "rule_id": "punctuation_01",
      "severity": "low",
      "finding": "标点符号重复：逗号连续出现两次 → 删除多余的逗号",
      "location": {{
        "page": {chunk['start_page']},
        "text_snippet": "各地区管理处、、工程部应按照有关规定进行检查",
        "region_description": "第{chunk['start_page']}页，第2章第3节"
      }},
      "points_deducted": 1
    }}
  ]
}}

⚠️ 不要包含 total_deductions, final_score, passed 等字段

## ⚠️ 验证清单（VLM 自查）
发送 JSON 前，请检查每个 violation：
□ text_snippet 是原文吗？（不是问题描述）
□ text_snippet 长度在 20-150 字符之间吗？
□ text_snippet 包含足够上下文吗？
□ text_snippet 没有 "(位置)" 等标记吗？
□ page 在 {chunk['start_page']}-{chunk['end_page']} 范围内吗？

如果任何一项不符合，修改后再输出！
"""
            
            try:
                violations = await self._call_vlm_simple(chunk_prompt, scenario_id)
                
                # 验证页码范围
                valid_violations = []
                for v in violations:
                    if chunk['start_page'] <= v.location.page <= chunk['end_page']:
                        valid_violations.append(v)
                    else:
                        logger.warning(
                            f"    ⚠ 过滤无效页码：violation页码{v.location.page}不在范围"
                            f"[{chunk['start_page']}-{chunk['end_page']}]内"
                        )
                
                return valid_violations
                
            except Exception as e:
                logger.error(f"    ✗ 块 {chunk_idx+1} 审核失败: {e}")
                return []
    
    # ========== 第3层：跨文档一致性检查 ==========
    
    async def _layer3_consistency_check(
        self,
        doc_structure: DocumentStructure,
        scenario_id: str
    ) -> List[Violation]:
        """
        第3层：跨文档一致性检查
        
        检查内容：
        - 术语统一性（"管理处" vs "分公司"）
        - 数据一致性（区段长、编号、时间）
        - 引用一致性
        """
        logger.info("  → 提取关键数据点...")
        
        # 提取关键信息
        key_terms = self._extract_key_terms(doc_structure)
        key_data = self._extract_key_data(doc_structure)
        
        consistency_prompt = f"""请检查以下文档的一致性问题。

## 术语使用情况
{key_terms}

## 关键数据出现情况
{key_data}

## 审核要点
1. **术语统一性**：
   - 检查术语是否统一使用（如"管理处"和"分公司"不应混用）
   - 检查缩写是否统一（如"QHSE"和"Q-HSE"不应混用）

2. **数据一致性**：
   - 关键数据在不同位置是否一致
   - 日期、编号、数量等是否前后统一

3. **逻辑一致性**：
   - 时间顺序是否合理
   - 引用内容是否与被引用内容一致

## 输出格式
只返回 violations 数组：

{{
  "violations": [
    {{
      "rule_id": "term_02",
      "severity": "medium",
      "finding": "术语使用不统一：'管理处'和'分公司'混用 → 统一使用'管理处'",
      "location": {{
        "page": 5,
        "text_snippet": "原文中包含不一致术语的文本片段（20-50字）",
        "region_description": "第5页，第3章"
      }},
      "points_deducted": 2
    }}
  ]
}}

⚠️ 不要包含 total_deductions, final_score, passed 等字段
"""
        
        logger.info("  → 调用VLM进行一致性分析...")
        violations = await self._call_vlm_simple(consistency_prompt, scenario_id)
        
        return violations
    
    def _extract_key_terms(self, doc_structure: DocumentStructure) -> str:
        """提取关键术语及其出现位置"""
        key_terms = ["管理处", "分公司", "作业区", "站队", "QHSE", "HSE", "Q-HSE"]
        
        term_occurrences = {}
        for term in key_terms:
            occurrences = []
            for page_struct in doc_structure.structure:
                for para in page_struct.paragraphs:
                    if term in para.text:
                        occurrences.append(f"第{page_struct.page}页")
                        break
            if occurrences:
                term_occurrences[term] = ', '.join(occurrences[:5])  # 只记录前5次
        
        if not term_occurrences:
            return "（未找到关键术语）"
        
        return '\n'.join([f"- '{term}': 出现在 {pages}" for term, pages in term_occurrences.items()])
    
    def _extract_key_data(self, doc_structure: DocumentStructure) -> str:
        """提取关键数据点"""
        data_points = []
        
        # 只检查前10页，避免信息过多
        for page_struct in doc_structure.structure[:10]:
            for para in page_struct.paragraphs:
                # 提取日期
                dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', para.text)
                if dates:
                    data_points.append(f"第{page_struct.page}页: 日期 {dates[0]}")
                
                # 提取编号
                codes = re.findall(r'[A-Z]{2,}-\d{4,}', para.text)
                if codes:
                    data_points.append(f"第{page_struct.page}页: 编号 {codes[0]}")
        
        if not data_points:
            return "（未提取到关键数据点）"
        
        return '\n'.join(data_points[:20])  # 最多20条
    
    # ========== 辅助方法 ==========
    
    async def _call_vlm_simple(
        self,
        prompt: str,
        scenario_id: str,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> List[Violation]:
        """
        简化的VLM调用
        
        Args:
            prompt: 审核prompt
            scenario_id: 场景ID
            images: 可选的图片列表
        
        Returns:
            violations列表
        """
        from openai import OpenAI
        
        client = OpenAI(
            base_url=self.vlm_client.config.vllm_base_url,
            api_key=self.vlm_client.config.vllm_api_key
        )
        
        # 获取规则文本
        rules_text = self.rule_engine.format_rules_for_prompt(scenario_id)
        
        # 系统prompt（简化版）
        system_prompt = f"""你是文档审核专家。请仔细检查文档，找出问题。

## 审核规则
{rules_text}

## 输出要求
- 仅报告发现的问题
- 每个问题必须包含：rule_id, severity, finding, location, points_deducted
- location必须包含准确的page和text_snippet（20-50字的原文精确文本）
- finding格式：问题描述 → 修改建议
"""
        
        try:
            response = client.chat.completions.create(
                model=self.vlm_client.config.vllm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=self.max_tokens_per_request,
                extra_body={
                    "guided_json": AuditResult.model_json_schema()
                }
            )
            
            content = response.choices[0].message.content
            
            # 清理响应内容：去除markdown代码块标记
            content = self._clean_json_response(content)
            
            # 解析JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                return []
            
            # ===== 关键修复：处理多种返回格式 =====
            violations_data = []
            
            # 格式1: {"violations": [...]}
            if isinstance(data, dict) and 'violations' in data:
                violations_data = data['violations']
            # 格式2: 直接是列表 [...]
            elif isinstance(data, list):
                violations_data = data
            # 格式3: 完整 AuditResult (向后兼容)
            elif isinstance(data, dict) and 'total_deductions' in data:
                violations_data = data.get('violations', [])
            else:
                logger.warning(f"未知返回格式")
                return []
            
            # 清洗并创建 Violation 对象
            violations = []
            for v_dict in violations_data:
                cleaned = self._clean_violation(v_dict)
                if cleaned:
                    try:
                        violation = Violation(**cleaned)
                        violations.append(violation)
                    except Exception as e:
                        logger.warning(f"创建 Violation 失败: {e}")
            
            return violations
            
        except Exception as e:
            logger.error(f"VLM调用失败: {e}")
            logger.debug(f"原始响应内容: {content[:500] if 'content' in locals() else 'N/A'}")
            return []
    
    def _clean_violation(self, v_dict: dict) -> dict:
        """
        清洗和验证 violation 数据（增强版）
        
        过滤条件：
        1. text_snippet 太短（< 15 字符）
        2. text_snippet 包含无效标记
        3. text_snippet 是页码列表
        4. 必需字段缺失
        """
        try:
            # 1. 检查必需字段
            required_fields = ['rule_id', 'severity', 'finding']
            for field in required_fields:
                if field not in v_dict:
                    logger.warning(f"violation缺少必需字段: {field}")
                    return None
            
            # 2. 处理 location 字段
            if 'location' in v_dict:
                location = v_dict['location']
                
                # 如果 location 是字符串，尝试解析
                if isinstance(location, str):
                    logger.debug(f"location 是字符串，尝试修复: {location[:50]}")
                    
                    # 提取页码
                    import re
                    page_match = re.search(r'第?(\d+)页', location)
                    page = int(page_match.group(1)) if page_match else 1
                    
                    location = {
                        'page': page,
                        'text_snippet': location[:100],
                        'region_description': f"第{page}页"
                    }
                    v_dict['location'] = location
                
                # 验证 location 对象
                if isinstance(location, dict):
                    # 确保有 page
                    if 'page' not in location:
                        location['page'] = 1
                    
                    # ===== 关键：验证和清洗 text_snippet =====
                    snippet = location.get('text_snippet', '')
                    
                    # 验证1：长度检查
                    if len(snippet) < 15:
                        logger.warning(f"❌ 过滤：text_snippet 太短（{len(snippet)}字符）: {snippet}")
                        return None
                    
                    # 验证2：检查无效标记
                    invalid_markers = ['(位置)', '(问题)', '[问题]', '错误：', '建议：']
                    if any(marker in snippet for marker in invalid_markers):
                        logger.warning(f"❌ 过滤：text_snippet 包含无效标记: {snippet[:50]}")
                        return None
                    
                    # 验证3：检查是否是页码列表
                    if snippet.count('第') > 2 and snippet.count('页') > 2:
                        logger.warning(f"❌ 过滤：text_snippet 是页码列表: {snippet[:50]}")
                        return None
                    
                    # 验证4：检查是否是 Markdown 标题
                    if snippet.strip().startswith('##') or snippet.strip().startswith('#'):
                        logger.warning(f"❌ 过滤：text_snippet 是 Markdown 标题: {snippet[:50]}")
                        return None
                    
                    # 验证5：检查是否只是页码标记
                    import re
                    if re.match(r'^[\s\-\d]+$', snippet.strip()):
                        logger.warning(f"❌ 过滤：text_snippet 只是页码: {snippet}")
                        return None
                    
                    # 验证6：检查是否是问题描述而非原文
                    problem_keywords = ['不合理', '不完整', '缺失', '错误', '问题', '建议']
                    if any(keyword in snippet for keyword in problem_keywords) and len(snippet) < 30:
                        logger.warning(f"❌ 过滤：text_snippet 疑似问题描述: {snippet}")
                        return None
                    
                    # 清洗：去除可能的标记
                    snippet = snippet.replace('(位置)', '').strip()
                    location['text_snippet'] = snippet[:200]  # 限制长度
                    
                    # 确保有 region_description
                    if 'region_description' not in location:
                        location['region_description'] = f"第{location['page']}页"
                    
                    v_dict['location'] = location
            else:
                # 完全没有 location，使用默认值
                logger.warning(f"violation 缺少 location 字段")
                v_dict['location'] = {
                    'page': 1,
                    'text_snippet': v_dict.get('finding', '未指定位置')[:50],
                    'region_description': '文档中'
                }
            
            # 3. 确保有 points_deducted
            if 'points_deducted' not in v_dict:
                v_dict['points_deducted'] = 1
            
            # 4. 限制 points_deducted 最大值（保险措施）
            v_dict['points_deducted'] = min(v_dict['points_deducted'], 5)
            
            return v_dict
            
        except Exception as e:
            logger.error(f"清洗 violation 时出错: {e}, 数据: {str(v_dict)[:100]}")
            return None
    
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
    
    def _build_audit_result(self, violations: List[Violation]) -> AuditResult:
        """构建最终审核结果（按维度权重+检查点封顶扣分）。"""

        # 归并到检查点并进行封顶
        deductions_by_checkpoint = {}
        for v in violations:
            # rule_id 即 checkpoint_id
            # 从 rule_engine 查询该检查点配置（可能不存在，容错为直接计分）
            cp_info = None
            try:
                cp_info = self.rule_engine.get_checkpoint_info(self.vlm_client.rule_engine.get_scenario('work_instruction_audit').scenario_id if False else '', v.rule_id)  # placeholder
            except Exception:
                cp_info = None

            # 更稳妥：直接使用本引擎持有的 rule_engine 查询两个场景之一
            if cp_info is None:
                # 尝试在所有场景中查找该 checkpoint
                for sid in self.rule_engine.get_all_scenario_ids():
                    info = self.rule_engine.get_checkpoint_info(sid, v.rule_id)
                    if info is not None:
                        cp_info = info
                        break

            # key 使用 (scenario_id, checkpoint_id)
            if cp_info:
                key = (cp_info['scenario_id'], v.rule_id)
                max_ded = cp_info['checkpoint'].max_deduction
            else:
                key = ('__unknown__', v.rule_id)
                max_ded = 5  # 未定义检查点的默认上限

            current = deductions_by_checkpoint.get(key, 0)
            current += max(0, v.points_deducted)
            deductions_by_checkpoint[key] = min(current, max_ded)

        # 按维度累计并受维度满分（权重×总分）约束
        deductions_by_dimension = {}
        for (scenario_id, checkpoint_id), ded in deductions_by_checkpoint.items():
            if scenario_id == '__unknown__':
                # 未知检查点直接归入一个“其他”维度，不做权重上限（但会受总上限保护）
                dim_key = ('__unknown__', '__others__')
                max_points = 100
            else:
                cp_info = self.rule_engine.get_checkpoint_info(scenario_id, checkpoint_id)
                dim_id = cp_info['dimension_id'] if cp_info else '__others__'
                dim_key = (scenario_id, dim_id)
                max_points = self.rule_engine.get_dimension_max_points(scenario_id, dim_id)

            current = deductions_by_dimension.get(dim_key, 0)
            current += ded
            deductions_by_dimension[dim_key] = min(current, max_points)

        total_deductions = sum(deductions_by_dimension.values())

        # 总扣分保护
        MAX_TOTAL_DEDUCTIONS = 80
        if total_deductions > MAX_TOTAL_DEDUCTIONS:
            logger.warning(f"⚠️ 总扣分 {total_deductions} 超过上限 {MAX_TOTAL_DEDUCTIONS}，已限制")
            total_deductions = MAX_TOTAL_DEDUCTIONS

        final_score = max(0, 100 - total_deductions)
        passed = final_score >= 60

        return AuditResult(
            violations=violations,
            total_deductions=total_deductions,
            final_score=final_score,
            passed=passed
        )

