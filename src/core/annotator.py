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
    
    # 可见 FreeText 注释的默认参数
    FREETEXT_MAX_WIDTH = 220
    FREETEXT_MIN_HEIGHT = 120
    FREETEXT_MAX_HEIGHT = 240
    FREETEXT_FONT_SIZE = 9
    ENABLE_HIGHLIGHT = False
    SIDEBAR_WIDTH = 220
    SIDEBAR_MARGIN = 10
    SIDEBAR_TOP = 40
    SIDEBAR_LINE_GAP = 6
    
    def __init__(self):
        # 每页边栏的纵向游标（用于栈式排布）
        self._sidebar_y_by_page = {}
        # 过滤掉不需要的规则前缀
        self.SKIP_RULE_PREFIXES = ("punctuation_",)
    
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
                # 过滤不需要标注的规则（如标点）
                if self._should_skip_violation(violation):
                    continue
                self._add_violation_annotation(
                    doc, 
                    violation, 
                    idx + 1,
                    fuzzy_threshold
                )
            except Exception as e:
                logger.warning(f"添加批注失败 (违规 {idx + 1}): {e}")
        
        # 保存 - 使用完整保存模式确保批注被正确写入
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # incremental=False: 完整保存而非增量保存，确保批注完整写入
        # deflate=True: 压缩保存，减小文件大小
        # garbage=4: 清理未使用对象
        doc.save(str(output_path), incremental=False, deflate=True, garbage=4)
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

            # 使用详细的批注内容，仅侧边栏呈现，避免任何叠加元素
            annotation_content = self._format_annotation_content(violation, violation_num)
            annotation_title = self._format_annotation_title(violation, violation_num)

            # 将正文内容写入“右侧边栏”，并画连线
            self._add_sidebar_annotation(
                page=page,
                anchor_rect=rect,
                title=annotation_title,
                content=annotation_content,
                color=color
            )
            
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
        """降级方案：在页面右侧添加可见 FreeText（避免重叠）"""
        # 根据违规编号计算Y坐标,每个批注间隔70px避免重叠
        y_offset = 50 + (violation_num - 1) * 70
        color = self.SEVERITY_COLORS.get(violation.severity, (1, 1, 0))

        annotation_content = self._format_annotation_content(violation, violation_num)
        annotation_title = self._format_annotation_title(violation, violation_num)

        # 构造一个靠右的锚点矩形，作为 FreeText 的参考
        anchor_width = 10
        x1 = page.rect.width - 60
        x0 = x1 - anchor_width
        anchor_rect = pymupdf.Rect(x0, y_offset, x1, y_offset + 20)

        # 写入边栏
        self._add_sidebar_annotation(
            page=page,
            anchor_rect=anchor_rect,
            title=annotation_title,
            content=annotation_content,
            color=color
        )

        # 仅侧边栏呈现，不放置任何气泡或高亮，避免重叠
    
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
                    
                    # 2. 添加边框高亮图片区域（仅绘制，不添加注释对象）
                    page.draw_rect(img_rect, color=color, width=2)

                    # 3. 为图片添加边栏说明
                    self._add_sidebar_annotation(
                        page=page,
                        anchor_rect=img_rect,
                        title=annotation_title,
                        content=annotation_content,
                        color=color
                    )
                    
                    logger.debug(f"图片批注添加成功: 问题 #{violation_num}")
                    return
            except Exception as e:
                logger.warning(f"获取图片位置失败: {e}")
        
        # 如果无法定位图片，使用一个合成的锚点矩形写入边栏（不放置气泡）
        center_point = pymupdf.Point(page.rect.width / 2, 100)
        anchor_rect = pymupdf.Rect(center_point.x, center_point.y, center_point.x + 10, center_point.y + 20)
        self._add_sidebar_annotation(
            page=page,
            anchor_rect=anchor_rect,
            title=annotation_title,
            content=annotation_content,
            color=color
        )
        
        logger.debug(f"图片批注添加成功（降级方案）: 问题 #{violation_num}")

    def _add_freetext_annotation(
        self,
        page: pymupdf.Page,
        anchor_rect: pymupdf.Rect,
        title: str,
        content: str,
        color: tuple
    ) -> None:
        """在 anchor_rect 附近添加可见 FreeText 注释。

        放置策略：优先放在右侧；如果越界则放左侧；再进行上下回退，确保在页内。
        """
        # 估算文本高度
        text_for_draw = self._compose_freetext_payload(title, content)
        est_lines = max(2, (len(text_for_draw) // 28) + 1)
        est_height = min(
            max(self.FREETEXT_MIN_HEIGHT, est_lines * 14 + 20),
            self.FREETEXT_MAX_HEIGHT
        )
        width = self.FREETEXT_MAX_WIDTH

        # 初始放置在右侧
        x0 = anchor_rect.x1 + 10
        y0 = anchor_rect.y0
        x1 = x0 + width
        y1 = y0 + est_height

        page_w = page.rect.width
        page_h = page.rect.height

        # 若右侧越界，改放左侧
        if x1 > page_w - 10:
            x1 = anchor_rect.x0 - 10
            x0 = x1 - width

        # 上下边界回退
        if y1 > page_h - 10:
            delta = (y1 - (page_h - 10))
            y0 = max(10, y0 - delta)
            y1 = y0 + est_height
        if y0 < 10:
            y0 = 10
            y1 = y0 + est_height

        rect = pymupdf.Rect(x0, y0, x1, y1)
        freetext = page.add_freetext_annot(
            rect,
            text_for_draw,
            fontsize=self.FREETEXT_FONT_SIZE,
            text_color=(0, 0, 0),
            fill_color=(1, 1, 1)
        )
        freettext_border_width = 0.7
        try:
            freetext.set_border(width=freettext_border_width)
        except Exception:
            pass
        freetext.set_colors(stroke=color, fill=(1, 1, 1))
        try:
            freetext.set_opacity(0.92)
        except Exception:
            pass
        freetext.set_flags(pymupdf.ANNOT_FLAG_PRINT)
        freetext.set_info(title=title, content=content, subject=title)
        freetext.update()

    def _compose_freetext_payload(self, title: str, content: str) -> str:
        """拼接 FreeText 展示文本（精简多行，控制长度）。"""
        max_chars = 550
        clean_content = content.replace("\r", "\n").strip()
        if len(clean_content) > max_chars:
            clean_content = clean_content[:max_chars] + "..."
        return f"{title}\n\n{clean_content}"

    def _get_sidebar_rect(self, page: pymupdf.Page) -> pymupdf.Rect:
        """返回本页右侧边栏矩形区域。若右侧放不下时尝试左侧。"""
        page_rect = page.rect
        right_x0 = page_rect.x1 - self.SIDEBAR_MARGIN - self.SIDEBAR_WIDTH
        right_x1 = page_rect.x1 - self.SIDEBAR_MARGIN
        if right_x0 > page_rect.x0 + self.SIDEBAR_MARGIN:
            return pymupdf.Rect(right_x0, self.SIDEBAR_TOP, right_x1, page_rect.y1 - self.SIDEBAR_MARGIN)
        # 退化到左侧边栏
        left_x0 = page_rect.x0 + self.SIDEBAR_MARGIN
        left_x1 = left_x0 + self.SIDEBAR_WIDTH
        return pymupdf.Rect(left_x0, self.SIDEBAR_TOP, left_x1, page_rect.y1 - self.SIDEBAR_MARGIN)

    def _add_sidebar_annotation(
        self,
        page: pymupdf.Page,
        anchor_rect: pymupdf.Rect,
        title: str,
        content: str,
        color: tuple
    ) -> None:
        """在页面右侧边栏区域追加一个 FreeText 区块，并用细线连接 anchor。"""
        sidebar_rect = self._get_sidebar_rect(page)
        page_id = id(page)
        current_y = self._sidebar_y_by_page.get(page_id, sidebar_rect.y0)

        payload = self._compose_freetext_payload(title, content)
        est_lines = max(2, (len(payload) // 28) + 1)
        box_h = min(max(self.FREETEXT_MIN_HEIGHT, est_lines * 14 + 20), self.FREETEXT_MAX_HEIGHT)

        # 若空间不足则从顶部重新开始（简单分页策略）
        if current_y + box_h + self.SIDEBAR_LINE_GAP > sidebar_rect.y1:
            current_y = sidebar_rect.y0

        box = pymupdf.Rect(sidebar_rect.x0, current_y, sidebar_rect.x1, current_y + box_h)
        freetext = page.add_freetext_annot(
            box, payload, fontsize=self.FREETEXT_FONT_SIZE, text_color=(0, 0, 0), fill_color=(1, 1, 1)
        )
        try:
            freetext.set_border(width=0.7)
        except Exception:
            pass
        freetext.set_colors(stroke=color, fill=(1, 1, 1))
        try:
            freetext.set_opacity(0.92)
        except Exception:
            pass
        freetext.set_flags(pymupdf.ANNOT_FLAG_PRINT)
        freetext.set_info(title=title, content=content, subject=title)
        freetext.update()

        # 连接线（从 anchor 到边栏框左边中点）
        anchor_point = anchor_rect.top_right + pymupdf.Point(2, 2)
        line_end = pymupdf.Point(box.x0, min(max(anchor_point.y, box.y0), box.y1))
        try:
            page.draw_line(anchor_point, line_end, color=color, width=0.6)
        except Exception:
            pass

        self._sidebar_y_by_page[page_id] = box.y1 + self.SIDEBAR_LINE_GAP

    def _should_skip_violation(self, violation: Violation) -> bool:
        """根据规则前缀判断是否跳过该违规。"""
        rule_id = violation.rule_id or ""
        return any(rule_id.startswith(prefix) for prefix in self.SKIP_RULE_PREFIXES)


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

