"""主 Pipeline 模块 - 异步流程编排"""
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .core.document_processor import DocumentProcessor
from .core.vlm_client import VLMClient
from .core.annotator import DocumentAnnotator
from .core.report_generator import ReportGenerator
from .models.schemas import AuditReport, ProcessingStage
from .utils.config import get_config
from .utils.logger import get_logger

logger = get_logger()


class DocumentAuditPipeline:
    """文档审核 Pipeline - 生产级实现"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = get_config(config_path)
        
        # 初始化各组件
        self.doc_processor = DocumentProcessor(
            output_dir=str(self.config.temp_dir)
        )
        self.vlm_client = VLMClient(config_path)
        self.annotator = DocumentAnnotator(
            temp_dir=str(self.config.temp_dir)
        )
        self.report_generator = ReportGenerator()
        
        # 创建输出目录
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Pipeline 初始化完成")
    
    async def process_document(
        self,
        document_path: str,
        scenario_id: str,
        output_name: Optional[str] = None
    ) -> AuditReport:
        """
        处理单个文档（主入口）
        
        Args:
            document_path: 文档路径
            scenario_id: 审核场景ID (work_instruction_audit 或 risk_management_audit)
            output_name: 输出文件名（可选）
        
        Returns:
            审核报告
        """
        start_time = time.time()
        timeout = self.config.pipeline_timeout
        
        logger.info(f"=" * 60)
        logger.info(f"开始处理文档: {document_path}")
        logger.info(f"审核场景: {scenario_id}")
        logger.info(f"超时限制: {timeout} 秒")
        logger.info(f"=" * 60)
        
        # 准备输出文件名
        doc_path = Path(document_path)
        if output_name is None:
            output_name = doc_path.stem
        
        stages = []
        
        try:
            # 阶段 1: 文档处理 (10-20s)
            stage1 = await self._run_with_timeout(
                self._stage_document_processing(document_path),
                timeout=20,
                stage_name="文档处理"
            )
            stages.append(stage1['stage'])
            doc_structure = stage1['result']['doc_structure']
            page_images = stage1['result']['page_images']
            
            # 检查剩余时间
            elapsed = time.time() - start_time
            if elapsed > timeout - 70:
                raise asyncio.TimeoutError(f"时间不足，已用 {elapsed:.1f}s")
            
            # 阶段 2: VLM 推理 (60-80s)
            stage2 = await self._run_with_timeout(
                self._stage_vlm_inference(doc_structure, page_images, scenario_id),
                timeout=80,
                stage_name="VLM 推理"
            )
            stages.append(stage2['stage'])
            audit_result = stage2['result']
            
            # 阶段 3: 批注生成 (5-10s)
            stage3 = await self._run_with_timeout(
                self._stage_annotation(document_path, audit_result, output_name),
                timeout=15,
                stage_name="批注生成"
            )
            stages.append(stage3['stage'])
            annotated_path = stage3['result']
            
            # 阶段 4: 报告生成 (2-5s)
            stage4 = await self._run_with_timeout(
                self._stage_report_generation(
                    doc_path.name, 
                    scenario_id,
                    audit_result, 
                    output_name
                ),
                timeout=10,
                stage_name="报告生成"
            )
            stages.append(stage4['stage'])
            report_path = stage4['result']
            
            # 生成审核报告
            total_time = time.time() - start_time
            
            audit_report = AuditReport(
                document_name=doc_path.name,
                audit_date=datetime.now(),
                auditor="AI审核系统",
                scenario_name=self._get_scenario_name(scenario_id),
                audit_result=audit_result,
                processing_time=total_time,
                annotated_document_path=annotated_path,
                report_path=report_path
            )
            
            logger.info(f"=" * 60)
            logger.info(f"处理完成！")
            logger.info(f"总耗时: {total_time:.2f} 秒")
            logger.info(f"最终得分: {audit_result.final_score}/100")
            logger.info(f"审核结果: {'通过' if audit_result.passed else '不通过'}")
            logger.info(f"发现问题: {len(audit_result.violations)} 个")
            logger.info(f"带批注文档: {annotated_path}")
            logger.info(f"审核报告: {report_path}")
            logger.info(f"=" * 60)
            
            return audit_report
            
        except asyncio.TimeoutError as e:
            logger.error(f"Pipeline 超时: {e}")
            raise
        except Exception as e:
            logger.error(f"Pipeline 执行失败: {e}", exc_info=True)
            raise
    
    async def _stage_document_processing(self, document_path: str) -> Dict[str, Any]:
        """阶段 1: 文档处理"""
        logger.info("[阶段 1/4] 文档处理开始...")
        
        # 提取文档结构
        doc_structure = await asyncio.to_thread(
            self.doc_processor.process_document,
            document_path
        )
        
        logger.info(f"文档解析完成: {doc_structure.page_count} 页")
        
        # 生成页面图片
        # 首先检查是否为 PDF，如果不是则需要转换
        doc_path = Path(document_path)
        if doc_path.suffix.lower() != '.pdf':
            # 使用临时转换的 PDF
            pdf_path = self.config.temp_dir / f"{doc_path.stem}.pdf"
            if not pdf_path.exists():
                logger.warning("需要 PDF 文件来生成页面图片")
                page_images = []
            else:
                page_images = await asyncio.to_thread(
                    self.doc_processor.generate_page_images,
                    str(pdf_path),
                    self.config.pipeline_dpi
                )
        else:
            page_images = await asyncio.to_thread(
                self.doc_processor.generate_page_images,
                document_path,
                self.config.pipeline_dpi
            )
        
        logger.info(f"页面图片生成完成: {len(page_images)} 张")
        
        return {
            'doc_structure': doc_structure,
            'page_images': page_images
        }
    
    async def _stage_vlm_inference(
        self,
        doc_structure,
        page_images,
        scenario_id: str
    ) -> Any:
        """阶段 2: VLM 推理"""
        logger.info("[阶段 2/4] VLM 推理开始...")
        
        # 调用 VLM 进行审核
        audit_result = await asyncio.to_thread(
            self.vlm_client.audit_document,
            doc_structure,
            page_images,
            scenario_id,
            self.config.pipeline_max_pages
        )
        
        logger.info(f"VLM 推理完成: 发现 {len(audit_result.violations)} 个问题")
        
        return audit_result
    
    async def _stage_annotation(
        self,
        source_path: str,
        audit_result,
        output_name: str
    ) -> str:
        """阶段 3: 批注生成"""
        logger.info("[阶段 3/4] 批注生成开始...")
        
        output_path = self.config.output_dir / f"{output_name}_annotated.pdf"
        
        annotated_path = await asyncio.to_thread(
            self.annotator.annotate_document,
            source_path,
            audit_result,
            str(output_path)
        )
        
        logger.info(f"批注生成完成: {annotated_path}")
        
        return annotated_path
    
    async def _stage_report_generation(
        self,
        doc_name: str,
        scenario_id: str,
        audit_result,
        output_name: str
    ) -> str:
        """阶段 4: 报告生成"""
        logger.info("[阶段 4/4] 报告生成开始...")
        
        output_path = self.config.output_dir / f"{output_name}_report.docx"
        
        # 构建 AuditReport
        audit_report = AuditReport(
            document_name=doc_name,
            audit_date=datetime.now(),
            auditor="AI审核系统",
            scenario_name=self._get_scenario_name(scenario_id),
            audit_result=audit_result,
            processing_time=0  # 临时值
        )
        
        report_path = await asyncio.to_thread(
            self.report_generator.generate_report,
            audit_report,
            str(output_path)
        )
        
        logger.info(f"报告生成完成: {report_path}")
        
        return report_path
    
    async def _run_with_timeout(
        self,
        coro,
        timeout: float,
        stage_name: str
    ) -> Dict[str, Any]:
        """
        运行协程并记录阶段信息
        
        Args:
            coro: 协程
            timeout: 超时时间
            stage_name: 阶段名称
        
        Returns:
            包含阶段信息和结果的字典
        """
        stage = ProcessingStage(stage_name=stage_name, status="running")
        
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            
            stage.end_time = datetime.now()
            stage.status = "completed"
            
            logger.info(f"{stage_name} 完成，耗时: {stage.duration:.2f}s")
            
            return {'stage': stage, 'result': result}
            
        except asyncio.TimeoutError:
            stage.end_time = datetime.now()
            stage.status = "failed"
            stage.error_message = f"超时 ({timeout}s)"
            
            logger.error(f"{stage_name} 超时！")
            raise
            
        except Exception as e:
            stage.end_time = datetime.now()
            stage.status = "failed"
            stage.error_message = str(e)
            
            logger.error(f"{stage_name} 失败: {e}")
            raise
    
    def _get_scenario_name(self, scenario_id: str) -> str:
        """获取场景名称"""
        scenario = self.vlm_client.rule_engine.get_scenario(scenario_id)
        return scenario.name if scenario else scenario_id
    
    def run_sync(
        self,
        document_path: str,
        scenario_id: str,
        output_name: Optional[str] = None
    ) -> AuditReport:
        """
        同步运行 Pipeline（便于非异步调用）
        
        Args:
            document_path: 文档路径
            scenario_id: 审核场景ID
            output_name: 输出文件名
        
        Returns:
            审核报告
        """
        return asyncio.run(
            self.process_document(document_path, scenario_id, output_name)
        )

