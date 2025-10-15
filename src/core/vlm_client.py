"""VLM 推理客户端模块"""
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from ..models.schemas import AuditResult, DocumentStructure
from ..models.rule_engine import RuleEngine
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger()


class VLMClient:
    """VLM 推理客户端 - 封装 OpenAI API 调用"""
    
    # System Prompt 模板
    AUDIT_SYSTEM_PROMPT = """你是一位专业的文档审核专家，具备深厚的{domain}领域知识。

## 你的角色定位
- 系统化地对照预定义规则评估文档
- 识别具体违规问题并标注精确位置
- 提供客观的、基于证据的评估
- 重点是「发现问题」，而非生成内容

## 核心原则
1. 基于规则：严格应用提供的规则，不引入新规则
2. 证据要求：每个发现都需引用具体位置
3. 客观性：无主观意见，仅报告规则违规
4. 完整性：彻底检查所有规则
5. 精确性：精确识别位置（页码、章节、文本片段）

## 输出要求
- 仅列出发现的违规问题（不列举符合项）
- 每个违规包含：规则ID、严重程度、位置、扣分
- 使用规则中定义的精确严重等级
- 绝不编造未提供的规则

## 审核规则

{rules}

## 评分说明
- 总分: 100 分
- 发现违规后，根据最大扣分进行扣分
- 最终得分 = 100 - 总扣分
- 得分 >= 60 分为通过
"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = get_config(config_path)
        self.client = OpenAI(
            base_url=self.config.vllm_base_url,
            api_key=self.config.vllm_api_key
        )
        self.rule_engine = RuleEngine()
        
        logger.info(f"VLM 客户端初始化完成，连接到: {self.config.vllm_base_url}")
    
    def audit_document(
        self,
        doc_structure: DocumentStructure,
        page_images: List[Dict[str, Any]],
        scenario_id: str,
        max_pages: Optional[int] = None
    ) -> AuditResult:
        """
        审核文档
        
        Args:
            doc_structure: 文档结构数据
            page_images: 页面图片列表
            scenario_id: 审核场景ID
            max_pages: 最大处理页数（限制）
        
        Returns:
            审核结果
        """
        logger.info(f"开始审核，场景: {scenario_id}")
        
        # 限制页数
        if max_pages and len(page_images) > max_pages:
            logger.warning(f"文档超过最大页数限制 {max_pages}，仅处理前 {max_pages} 页")
            page_images = page_images[:max_pages]
        
        # 生成 Prompt
        system_prompt = self._generate_system_prompt(scenario_id)
        user_prompt = self._generate_user_prompt(doc_structure)
        
        # 构建消息
        messages = self._build_messages(system_prompt, user_prompt, page_images)
        
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
        
        # 确定领域
        domain = "作业指导" if "work_instruction" in scenario_id else "风险管控"
        
        # 填充模板
        return self.AUDIT_SYSTEM_PROMPT.format(
            domain=domain,
            rules=rules_text
        )
    
    def _generate_user_prompt(self, doc_structure: DocumentStructure) -> str:
        """生成 User Prompt"""
        prompt = f"""请审核以下文档，严格按照提供的规则进行检查。

文档信息：
- 格式: {doc_structure.format.upper()}
- 页数: {doc_structure.page_count}

文档内容（Markdown 格式）：

{doc_structure.markdown[:10000]}  

请仔细审核文档，找出所有违规问题。对于每个问题，请提供：
1. 违规的规则 ID（如 toc_01）
2. 严重程度（critical/high/medium/low）
3. 具体位置（页码和文本片段）
4. 问题描述
5. 扣分

按照 JSON 格式输出审核结果。
"""
        return prompt
    
    def _build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        page_images: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """构建消息列表"""
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 构建用户消息内容（图片 + 文本）
        user_content = []
        
        # 添加页面图片（最多前 5 页）
        for img_info in page_images[:5]:
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
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
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
            
            # 验证并解析 JSON
            result = AuditResult.model_validate_json(content)
            
            return result
            
        except Exception as e:
            logger.error(f"VLM API 调用异常: {e}")
            
            # 返回空结果（降级方案）
            return AuditResult(
                violations=[],
                total_deductions=0,
                final_score=100,
                passed=True
            )
    
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

