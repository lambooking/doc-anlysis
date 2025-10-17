"""Pydantic 数据模型定义"""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime


# ==================== 审核规则模型 ====================

class Checkpoint(BaseModel):
    """审核检查点"""
    checkpoint_id: str = Field(..., description="检查点ID")
    description: str = Field(..., description="检查点描述")
    severity: Literal["critical", "high", "medium", "low"] = Field(..., description="严重程度")
    max_deduction: int = Field(ge=0, le=100, description="最大扣分")


class AuditItem(BaseModel):
    """审核项"""
    item_id: str = Field(..., description="审核项ID")
    name: str = Field(..., description="审核项名称")
    checkpoints: List[Checkpoint] = Field(default_factory=list, description="检查点列表")


class AuditDimension(BaseModel):
    """审核维度"""
    dimension_id: str = Field(..., description="维度ID")
    name: str = Field(..., description="维度名称")
    weight: float = Field(ge=0, le=1, description="权重")
    items: List[AuditItem] = Field(default_factory=list, description="审核项列表")


class AuditScenario(BaseModel):
    """审核场景"""
    scenario_id: str = Field(..., description="场景ID")
    name: str = Field(..., description="场景名称")
    total_points: int = Field(default=100, description="总分")
    dimensions: List[AuditDimension] = Field(default_factory=list, description="审核维度列表")


class AuditRuleConfig(BaseModel):
    """审核规则配置"""
    version: str = Field(default="1.0", description="配置版本")
    audit_scenarios: List[AuditScenario] = Field(default_factory=list, description="审核场景列表")


# ==================== 审核结果模型 ====================

class LocationEncoding(BaseModel):
    """位置编码"""
    page: int = Field(ge=1, description="页码")
    text_snippet: str = Field(min_length=1, max_length=200, description="文本片段")  # 放宽最小长度限制为1
    region_description: str = Field(..., description="区域描述")


class Violation(BaseModel):
    """审核违规"""
    rule_id: str = Field(..., description="规则ID")
    severity: Literal["critical", "high", "medium", "low"] = Field(..., description="严重程度")
    location: LocationEncoding = Field(..., description="位置信息")
    finding: str = Field(..., description="发现的问题")
    points_deducted: int = Field(ge=0, description="扣分")


class AuditResult(BaseModel):
    """完整审核结果"""
    violations: List[Violation] = Field(default_factory=list, description="违规列表")
    total_deductions: int = Field(ge=0, description="总扣分")
    final_score: int = Field(ge=0, le=100, description="最终得分")
    passed: bool = Field(..., description="是否通过")


# ==================== 文档处理模型 ====================

class ParagraphInfo(BaseModel):
    """段落信息"""
    index: int = Field(..., description="段落索引")
    bbox: Optional[List[float]] = Field(default=None, description="边界框坐标 [x0, y0, x1, y1]")
    text: str = Field(..., description="段落文本")


class TableInfo(BaseModel):
    """表格信息"""
    index: int = Field(..., description="表格索引")
    bbox: Optional[List[float]] = Field(default=None, description="边界框坐标 [x0, y0, x1, y1]")
    data: List[List[str]] = Field(default_factory=list, description="表格数据")


class ImageInfo(BaseModel):
    """图片信息"""
    index: int = Field(..., description="图片索引")
    bbox: Optional[List[float]] = Field(default=None, description="边界框坐标 [x0, y0, x1, y1]")
    image_path: Optional[str] = Field(default=None, description="图片路径")


class PageStructure(BaseModel):
    """页面结构"""
    page: int = Field(ge=1, description="页码")
    paragraphs: List[ParagraphInfo] = Field(default_factory=list, description="段落列表")
    tables: List[TableInfo] = Field(default_factory=list, description="表格列表")
    images: List[ImageInfo] = Field(default_factory=list, description="图片列表")


class DocumentStructure(BaseModel):
    """文档结构"""
    markdown: str = Field(..., description="Markdown 格式文本")
    structure: List[PageStructure] = Field(default_factory=list, description="页面结构列表")
    format: Literal["pdf", "docx", "doc"] = Field(..., description="文档格式")
    page_count: int = Field(ge=1, description="页数")


# ==================== Pipeline 模型 ====================

class ProcessingStage(BaseModel):
    """处理阶段"""
    stage_name: str = Field(..., description="阶段名称")
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    status: Literal["pending", "running", "completed", "failed"] = Field(default="pending", description="状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    
    @property
    def duration(self) -> float:
        """计算持续时间（秒）"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class AuditReport(BaseModel):
    """审核报告"""
    document_name: str = Field(..., description="文档名称")
    audit_date: datetime = Field(default_factory=datetime.now, description="审核日期")
    auditor: str = Field(default="AI审核系统", description="审核人")
    scenario_name: str = Field(..., description="审核场景名称")
    audit_result: AuditResult = Field(..., description="审核结果")
    processing_time: float = Field(ge=0, description="处理时间（秒）")
    annotated_document_path: Optional[str] = Field(default=None, description="带批注文档路径")
    report_path: Optional[str] = Field(default=None, description="报告路径")

