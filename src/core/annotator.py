"""批注生成器模块"""
import pymupdf
from pathlib import Path
from typing import List, Optional
from fuzzywuzzy import fuzz
from ..models.schemas import AuditResult, Violation
from ..utils.logger import get_logger

logger = get_logger()


class PDFAnnotator:
    """PDF 批注生成器"""
    
    # 严重程度对应颜色（RGB 0-1）
    SEVERITY_COLORS = {
        'critical': (1, 0, 0),      # 红色
        'high': (1, 0.5, 0),        # 橙色
        'medium': (1, 1, 0),        # 黄色
        'low': (0.5, 1, 0)          # 绿色
    }
    
    def __init__(self):
        pass
    
    def _format_annotation_title(self, violation: Violation, num: int) -> str:
        """格式化批注标题,让评委一眼看懂"""
        # 提取问题描述(去掉修改建议部分)
        if "→" in violation.finding:
            problem = violation.finding.split("→")[0].strip()
        elif "应为" in violation.finding:
            problem = violation.finding.split("应为")[0].strip()
        else:
            problem = violation.finding
        
        # 截取前25个字符
        short_problem = problem[:25] + "..." if len(problem) > 25 else problem
        
        # 组装标题: 序号 + 扣分 + 问题
        return f"#{num} (-{violation.points_deducted}分) {short_problem}"
    
    def annotate_pdf(
        self,
        pdf_path: str,
        audit_result: AuditResult,
        output_path: str,
        fuzzy_threshold: int = 80
    ) -> str:
        """
        在 PDF 中添加批注
        
        Args:
            pdf_path: 原始 PDF 路径
            audit_result: 审核结果
            output_path: 输出 PDF 路径
            fuzzy_threshold: 模糊匹配阈值
        
        Returns:
            输出文件路径
        """
        logger.info(f"开始添加批注到 PDF: {pdf_path}")
        
        doc = pymupdf.open(pdf_path)
        
        # 为每个违规添加批注
        for idx, violation in enumerate(audit_result.violations):
            try:
                self._add_violation_annotation(
                    doc, 
                    violation, 
                    idx + 1,
                    fuzzy_threshold
                )
            except Exception as e:
                logger.warning(f"添加批注失败 (违规 {idx + 1}): {e}")
        
        # 保存
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        doc.close()
        
        logger.info(f"批注添加完成，共 {len(audit_result.violations)} 处，保存到: {output_path}")
        
        return str(output_path)
    
    def _add_violation_annotation(
        self,
        doc: pymupdf.Document,
        violation: Violation,
        violation_num: int,
        fuzzy_threshold: int
    ):
        """添加单个违规批注（增强版）"""
        page_num = violation.location.page - 1
        
        if page_num < 0 or page_num >= len(doc):
            logger.warning(f"页码超出范围: {violation.location.page}")
            return
        
        page = doc[page_num]
        search_text = violation.location.text_snippet
        
        # 检查是否是图片问题
        if search_text.startswith("[第") and "图]" in search_text:
            # 特殊处理图片批注
            self._add_image_annotation(page, violation, violation_num)
            return
        
        # 尝试精确搜索
        rects = page.search_for(search_text)
        
        # 如果精确搜索失败，尝试模糊匹配
        if not rects:
            logger.debug(f"精确搜索失败，尝试模糊匹配: {search_text[:50]}...")
            rects = self._fuzzy_search(page, search_text, fuzzy_threshold)
        
        if rects:
            # 使用第一个匹配的位置
            rect = rects[0]
            color = self.SEVERITY_COLORS.get(violation.severity, (1, 1, 0))
            
            # 添加高亮
            highlight = page.add_highlight_annot(rect)
            highlight.set_colors(stroke=color)
            highlight.set_opacity(0.5)
            
            # 使用详细的批注内容
            annotation_content = self._format_annotation_content(violation, violation_num)
            annotation_title = self._format_annotation_title(violation, violation_num)
            
            # 设置高亮批注的信息（使用 info 字典）
            highlight.info["title"] = annotation_title
            highlight.info["content"] = annotation_content
            highlight.info["subject"] = annotation_title
            highlight.update()
            
            # 在旁边添加气泡标记（更显眼）- 去除表情符号
            point = rect.top_right + pymupdf.Point(10, 0)  # 右侧10px
            note = page.add_text_annot(point, f"#{violation_num}")
            note.set_colors(stroke=color)
            
            # 设置气泡批注的信息（使用 info 字典）
            note.info["title"] = annotation_title
            note.info["content"] = annotation_content
            note.info["subject"] = annotation_title
            note.update()
            
            logger.debug(f"批注添加成功: 问题 #{violation_num} 在第 {violation.location.page} 页")
        else:
            # 如果找不到位置，在页面顶部添加文本批注
            logger.warning(f"无法定位文本，在页面顶部添加批注: {search_text[:50]}...")
            self._add_fallback_annotation(page, violation, violation_num)
    
    def _fuzzy_search(
        self,
        page: pymupdf.Page,
        search_text: str,
        threshold: int
    ) -> List[pymupdf.Rect]:
        """
        模糊匹配搜索文本
        
        Args:
            page: PDF 页面
            search_text: 搜索文本
            threshold: 相似度阈值（0-100）
        
        Returns:
            匹配的矩形区域列表
        """
        blocks = page.get_text("blocks")
        
        best_match = None
        best_score = 0
        
        for x0, y0, x1, y1, text, *_ in blocks:
            # 计算相似度
            similarity = fuzz.ratio(
                search_text.lower().strip(),
                text.lower().strip()
            )
            
            if similarity > best_score and similarity >= threshold:
                best_score = similarity
                best_match = pymupdf.Rect(x0, y0, x1, y1)
        
        if best_match:
            logger.debug(f"模糊匹配成功，相似度: {best_score}%")
            return [best_match]
        
        return []
    
    def _add_fallback_annotation(
        self,
        page: pymupdf.Page,
        violation: Violation,
        violation_num: int
    ):
        """降级方案：在页面顶部添加文本批注"""
        # 在页面右上角添加便签
        point = pymupdf.Point(page.rect.width - 50, 50)
        color = self.SEVERITY_COLORS.get(violation.severity, (1, 1, 0))
        
        annotation_content = self._format_annotation_content(violation, violation_num)
        annotation_title = self._format_annotation_title(violation, violation_num)
        
        note = page.add_text_annot(point, f"问题 #{violation_num}")
        note.set_colors(stroke=color)
        
        # 使用 info 字典设置批注信息
        note.info["title"] = annotation_title
        note.info["content"] = annotation_content
        note.info["subject"] = annotation_title
        note.update()
    
    def _format_annotation_content(self, violation: Violation, num: int) -> str:
        """
        格式化批注内容（评委重点看这个）
        
        返回格式：
        【问题描述】
        具体问题...
        
        【扣分】
        X分
        
        【修改建议】
        应该...
        """
        # 从finding中提取问题和建议
        finding = violation.finding
        
        # 如果finding中包含"→"或"应为"，分离问题和建议
        if "→" in finding:
            problem, suggestion = finding.split("→", 1)
            problem = problem.strip()
            suggestion = suggestion.strip()
        elif "应为" in finding:
            problem, suggestion = finding.split("应为", 1)
            problem = problem.strip()
            suggestion = f"应为{suggestion.strip()}"
        else:
            problem = finding
            suggestion = "请参考相关规范进行修正"
        
        # 简化严重程度标签
        severity_map = {
            'critical': '关键',
            'high': '高',
            'medium': '中',
            'low': '低'
        }
        severity_text = severity_map.get(violation.severity, violation.severity)
        
        # ✅ 极简格式，不使用特殊字符
        content = (
            f"问题: {problem}\n\n"
            f"级别: {severity_text}优先级\n\n"
            f"扣分: {violation.points_deducted}分\n\n"
            f"建议: {suggestion}\n\n"
            f"规则: {violation.rule_id}"
        )
        
        return content
    
    def _severity_label(self, severity: str) -> str:
        """严重程度标签（简化版）"""
        labels = {
            'critical': '关键',
            'high': '高',
            'medium': '中',
            'low': '低'
        }
        return labels.get(severity, severity)
    
    def _add_image_annotation(
        self,
        page: pymupdf.Page,
        violation: Violation,
        violation_num: int
    ):
        """
        为图片问题添加批注
        
        处理 text_snippet 为 "[第X页XX图]" 格式的情况
        """
        # 在图片上添加箭头或圈注
        # 1. 识别图片区域
        image_list = page.get_images()
        
        color = self.SEVERITY_COLORS.get(violation.severity, (1, 1, 0))
        annotation_content = self._format_annotation_content(violation, violation_num)
        annotation_title = self._format_annotation_title(violation, violation_num)
        
        if image_list:
            # 取第一个图片区域
            try:
                img_info = image_list[0]
                # 获取图片在页面上的位置
                img_rects = page.get_image_rects(img_info[0])
                
                if img_rects:
                    img_rect = img_rects[0]
                    
                    # 2. 在图片右上角添加醒目标记 - 去除表情符号
                    marker_point = img_rect.top_right + pymupdf.Point(5, 5)
                    note = page.add_text_annot(marker_point, f"图片问题#{violation_num}")
                    note.set_colors(stroke=color)
                    
                    # 使用 info 字典设置批注信息
                    note.info["title"] = annotation_title
                    note.info["content"] = annotation_content
                    note.info["subject"] = annotation_title
                    note.update()
                    
                    # 3. 添加边框高亮图片区域
                    page.draw_rect(img_rect, color=color, width=2)
                    
                    logger.debug(f"图片批注添加成功: 问题 #{violation_num}")
                    return
            except Exception as e:
                logger.warning(f"获取图片位置失败: {e}")
        
        # 如果无法定位图片，在页面中央添加批注
        center_point = pymupdf.Point(page.rect.width / 2, 100)
        note = page.add_text_annot(center_point, f"图片问题 #{violation_num}")
        note.set_colors(stroke=color)
        
        # 使用 info 字典设置批注信息
        note.info["title"] = annotation_title
        note.info["content"] = annotation_content
        note.info["subject"] = annotation_title
        note.update()
        
        logger.debug(f"图片批注添加成功（降级方案）: 问题 #{violation_num}")


class DocumentAnnotator:
    """文档批注生成器 - 统一入口"""
    
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_annotator = PDFAnnotator()
    
    def annotate_document(
        self,
        source_path: str,
        audit_result: AuditResult,
        output_path: str
    ) -> str:
        """
        为文档添加批注（自动处理格式转换）
        
        Args:
            source_path: 源文档路径
            audit_result: 审核结果
            output_path: 输出路径
        
        Returns:
            带批注文档的路径
        """
        source_path = Path(source_path)
        suffix = source_path.suffix.lower()
        
        # 如果不是 PDF，先转换
        if suffix in ['.doc', '.docx']:
            logger.info(f"文档需要转换为 PDF: {source_path.name}")
            pdf_path = self._convert_to_pdf(source_path)
            if not pdf_path:
                raise RuntimeError(f"文档转 PDF 失败: {source_path}")
        else:
            pdf_path = source_path
        
        # 添加批注
        return self.pdf_annotator.annotate_pdf(
            str(pdf_path),
            audit_result,
            output_path
        )
    
    def _convert_to_pdf(self, doc_path: Path) -> Optional[Path]:
        """转换文档为 PDF"""
        import subprocess
        import shutil
        
        output_pdf = self.temp_dir / f"{doc_path.stem}_converted.pdf"
        
        # 尝试使用 LibreOffice
        if shutil.which("soffice") or shutil.which("libreoffice"):
            try:
                cmd = [
                    "soffice" if shutil.which("soffice") else "libreoffice",
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(self.temp_dir),
                    str(doc_path)
                ]
                
                result = subprocess.run(
                    cmd,
                    timeout=30,
                    capture_output=True,
                    text=True
                )
                
                # LibreOffice 会使用原文件名
                expected_pdf = self.temp_dir / f"{doc_path.stem}.pdf"
                if expected_pdf.exists():
                    if expected_pdf != output_pdf:
                        expected_pdf.rename(output_pdf)
                    return output_pdf
                    
            except Exception as e:
                logger.warning(f"LibreOffice 转换失败: {e}")
        
        # 尝试 docx2pdf
        try:
            from docx2pdf import convert
            convert(str(doc_path), str(output_pdf))
            if output_pdf.exists():
                return output_pdf
        except Exception as e:
            logger.warning(f"docx2pdf 转换失败: {e}")
        
        return None

