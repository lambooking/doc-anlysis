"""测试分层审核功能"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import DocumentAuditPipeline
from src.utils.logger import get_logger

logger = get_logger()


def test_short_document():
    """测试短文档（≤20页）- 应该使用标准审核"""
    logger.info("=" * 60)
    logger.info("测试1: 短文档（标准审核）")
    logger.info("=" * 60)
    
    # 这里需要一个实际的短文档路径
    # doc_path = "path/to/short_document.pdf"
    # pipeline = DocumentAuditPipeline()
    # report = pipeline.run_sync(doc_path, "work_instruction_audit")
    # print(f"结果: 发现 {len(report.audit_result.violations)} 个问题")
    
    logger.info("⚠ 请提供实际的短文档路径进行测试")


def test_long_document():
    """测试长文档（>20页）- 应该使用分层审核"""
    logger.info("=" * 60)
    logger.info("测试2: 长文档（分层审核）")
    logger.info("=" * 60)
    
    # 这里需要一个实际的长文档路径（如80页的文档）
    # doc_path = "path/to/long_document.pdf"
    # pipeline = DocumentAuditPipeline()
    # report = pipeline.run_sync(doc_path, "work_instruction_audit")
    # print(f"结果: 发现 {len(report.audit_result.violations)} 个问题")
    
    logger.info("⚠ 请提供实际的长文档路径进行测试")


def test_configuration():
    """测试配置加载"""
    logger.info("=" * 60)
    logger.info("测试3: 配置加载")
    logger.info("=" * 60)
    
    from src.utils.config import get_config
    
    config = get_config()
    
    logger.info(f"✓ VLM配置:")
    logger.info(f"  - base_url: {config.vllm_base_url}")
    logger.info(f"  - model: {config.vllm_model}")
    logger.info(f"  - max_tokens: {config.vllm_max_tokens}")
    
    logger.info(f"✓ 分层审核配置:")
    logger.info(f"  - enabled: {config.layered_audit_enabled}")
    logger.info(f"  - chunk_size: {config.layered_audit_chunk_size}")
    logger.info(f"  - max_concurrent_chunks: {config.layered_audit_max_concurrent_chunks}")
    logger.info(f"  - trigger_page_count: {config.layered_audit_trigger_page_count}")
    
    logger.info(f"✓ Pipeline配置:")
    logger.info(f"  - timeout: {config.pipeline_timeout}秒")
    logger.info(f"  - dpi: {config.pipeline_dpi}")


if __name__ == "__main__":
    # 测试配置加载
    test_configuration()
    
    print("\n" + "=" * 60)
    print("配置测试完成！")
    print("=" * 60)
    print("\n要测试实际审核功能，请：")
    print("1. 确保vLLM服务已启动")
    print("2. 准备测试文档（短文档≤20页，长文档>20页）")
    print("3. 修改test_short_document()和test_long_document()中的文档路径")
    print("4. 运行: python test_layered_audit.py")

