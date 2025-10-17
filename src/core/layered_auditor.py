"""分层审核引擎 - 解决超长文档问题"""
import asyncio
import re
from typing import List, Dict, Any
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
仅报告发现的结构性问题，使用JSON格式。如果没有问题，返回空的violations列表。
每个问题必须包含：
- rule_id: 对应的检查点ID（如toc_01, num_01, logic_01）
- severity: 严重程度
- finding: 具体问题描述
- location: 包含page（估算页码）、text_snippet（章节标题）、region_description
- points_deducted: 扣分
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
            
            # 构建针对该块的prompt
            chunk_prompt = f"""请审核以下文档片段（第{chunk['start_page']}-{chunk['end_page']}页）。

## 文档片段内容
{chunk['text']}

## 审核重点
1. **语法检查**：
   - 标点符号错误（逗号重复、括号不匹配、句号缺失）
   - 语句不通顺（病句、歧义句、不完整句）
   - 专业术语拼写错误或不统一

2. **逻辑检查**：
   - 上下文是否连贯
   - 时间顺序是否合理
   - 前后是否矛盾

3. **内容检查**：
   - 操作步骤是否完整清晰
   - 安全注意事项是否充分
   - 关键步骤是否缺失

## 重要说明
⚠️ 这是第{chunk['start_page']}-{chunk['end_page']}页的内容
⚠️ location.page 必须在 {chunk['start_page']} 到 {chunk['end_page']} 范围内
⚠️ text_snippet 必须是原文精确文本，长度至少20字，包含问题前后的完整上下文
   - ✅ 好的例子："各地区管理处、、工程部应按照有关规定进行检查"（包含错误和上下文）
   - ❌ 坏的例子："、、"（太短，无法定位）
⚠️ finding 必须包含具体问题描述和修改建议，用" → "分隔

## 输出格式
返回JSON格式的violations列表。如果没有问题，返回空列表。
每个violation必须包含：
- rule_id: 对应的规则ID
- severity: 严重程度
- finding: 问题描述 → 修改建议
- location: {{page, text_snippet, region_description}}
- points_deducted: 扣分
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
仅报告不一致的问题，返回JSON格式的violations列表。
每个violation必须包含：
- rule_id: term_02（术语统一性）或 logic_02（前后矛盾）等
- severity: 严重程度
- finding: 具体的不一致问题 → 修改建议
- location: 包含page、text_snippet、region_description
- points_deducted: 扣分
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
        scenario_id: str
    ) -> List[Violation]:
        """
        简化的VLM调用（不带图片）
        
        Args:
            prompt: 审核prompt
            scenario_id: 场景ID
        
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
            import json
            parsed = json.loads(content)
            
            # VLM可能直接返回violations数组，也可能返回完整的AuditResult对象
            if isinstance(parsed, list):
                # 直接返回的是violations数组
                from ..models.schemas import Violation
                violations = []
                for v_dict in parsed:
                    # 修复和清洗violation数据
                    v_dict = self._sanitize_violation(v_dict)
                    if v_dict:  # 只添加有效的violation
                        try:
                            violations.append(Violation(**v_dict))
                        except Exception as e:
                            logger.warning(f"无法解析violation: {e}, 数据: {v_dict}")
                            continue
                return violations
            elif isinstance(parsed, dict):
                # 返回的是完整对象
                result = AuditResult(**parsed)
                # 同样修复violations中的text_snippet
                for v in result.violations:
                    if len(v.location.text_snippet) < 10:
                        v.location.text_snippet = f"{v.location.text_snippet} (问题位置)"
                return result.violations
            else:
                logger.warning(f"未预期的响应格式: {type(parsed)}")
                return []
            
        except Exception as e:
            logger.error(f"VLM调用失败: {e}")
            logger.debug(f"原始响应内容: {content[:500] if 'content' in locals() else 'N/A'}")
            return []
    
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
                logger.warning(f"violation缺少必需字段，跳过: {v_dict}")
                return None
            
            # 修复location字段
            if 'location' in v_dict:
                location = v_dict['location']
                
                # 如果location是字符串，尝试构建location对象
                if isinstance(location, str):
                    logger.warning(f"location是字符串，尝试修复: {location}")
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
            logger.error(f"清洗violation数据时出错: {e}, 数据: {v_dict}")
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
        """构建最终审核结果"""
        total_deductions = sum(v.points_deducted for v in violations)
        final_score = max(0, 100 - total_deductions)
        passed = final_score >= 60
        
        return AuditResult(
            violations=violations,
            total_deductions=total_deductions,
            final_score=final_score,
            passed=passed
        )

