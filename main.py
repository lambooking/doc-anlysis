"""主入口程序 - CLI 命令行工具"""
import argparse
import sys
from pathlib import Path

from src.pipeline import DocumentAuditPipeline
from src.utils.logger import get_logger, setup_logger
from src.utils.config import get_config

# 设置日志
config = get_config()
logger = setup_logger(
    level=config.log_level,
    log_format=config.log_format,
    log_file=config.log_file
)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='文档智能审核系统 - 基于 Qwen-2.5-VL 7B',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 审核作业指导书
  python main.py document.pdf --scenario work_instruction_audit
  
  # 审核风险管控方案
  python main.py risk_plan.docx --scenario risk_management_audit
  
  # 指定输出名称
  python main.py document.pdf --scenario work_instruction_audit --output my_audit
  
审核场景ID:
  - work_instruction_audit: 作业指导书审核
  - risk_management_audit: 风险管控方案审核
        """
    )
    
    parser.add_argument(
        'document',
        type=str,
        help='要审核的文档路径 (支持 PDF, DOCX, DOC 格式)'
    )
    
    parser.add_argument(
        '--scenario',
        '-s',
        type=str,
        required=True,
        choices=['work_instruction_audit', 'risk_management_audit'],
        help='审核场景ID'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        default=None,
        help='输出文件名前缀（可选）'
    )
    
    parser.add_argument(
        '--config',
        '-c',
        type=str,
        default='config/config.yaml',
        help='配置文件路径（默认: config/config.yaml）'
    )
    
    args = parser.parse_args()
    
    # 检查文档是否存在
    doc_path = Path(args.document)
    if not doc_path.exists():
        logger.error(f"文档不存在: {args.document}")
        sys.exit(1)
    
    # 检查文档格式
    if doc_path.suffix.lower() not in ['.pdf', '.docx', '.doc']:
        logger.error(f"不支持的文档格式: {doc_path.suffix}")
        logger.error("支持的格式: PDF, DOCX, DOC")
        sys.exit(1)
    
    try:
        # 创建 Pipeline
        logger.info("初始化审核系统...")
        pipeline = DocumentAuditPipeline(config_path=args.config)
        
        # 执行审核
        logger.info(f"开始审核文档: {doc_path.name}")
        report = pipeline.run_sync(
            document_path=str(doc_path),
            scenario_id=args.scenario,
            output_name=args.output
        )
        
        # 显示结果
        print("\n" + "=" * 70)
        print("审核完成！")
        print("=" * 70)
        print(f"文档名称: {report.document_name}")
        print(f"审核场景: {report.scenario_name}")
        print(f"处理时间: {report.processing_time:.2f} 秒")
        print(f"最终得分: {report.audit_result.final_score}/100")
        print(f"审核结果: {'✓ 通过' if report.audit_result.passed else '✗ 不通过'}")
        print(f"发现问题: {len(report.audit_result.violations)} 个")
        print(f"总扣分: {report.audit_result.total_deductions} 分")
        print("-" * 70)
        print(f"带批注文档: {report.annotated_document_path}")
        print(f"审核报告: {report.report_path}")
        print("=" * 70)
        
        # 显示问题摘要
        if report.audit_result.violations:
            print("\n问题摘要:")
            severity_counts = {
                'critical': sum(1 for v in report.audit_result.violations if v.severity == 'critical'),
                'high': sum(1 for v in report.audit_result.violations if v.severity == 'high'),
                'medium': sum(1 for v in report.audit_result.violations if v.severity == 'medium'),
                'low': sum(1 for v in report.audit_result.violations if v.severity == 'low')
            }
            
            if severity_counts['critical'] > 0:
                print(f"  • 关键问题: {severity_counts['critical']} 个")
            if severity_counts['high'] > 0:
                print(f"  • 高优先级: {severity_counts['high']} 个")
            if severity_counts['medium'] > 0:
                print(f"  • 中优先级: {severity_counts['medium']} 个")
            if severity_counts['low'] > 0:
                print(f"  • 低优先级: {severity_counts['low']} 个")
        
        print("\n详细信息请查看审核报告。\n")
        
        # 返回状态码
        sys.exit(0 if report.audit_result.passed else 1)
        
    except KeyboardInterrupt:
        logger.warning("用户中断")
        sys.exit(130)
    except Exception as e:
        logger.error(f"审核失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

