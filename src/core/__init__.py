"""核心模块"""
from .document_processor import DocumentProcessor
from .vlm_client import VLMClient
from .annotator import PDFAnnotator, DocumentAnnotator
from .report_generator import ReportGenerator

__all__ = [
    'DocumentProcessor',
    'VLMClient',
    'PDFAnnotator',
    'DocumentAnnotator',
    'ReportGenerator'
]

