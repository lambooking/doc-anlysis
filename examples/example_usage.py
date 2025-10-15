"""使用示例"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline import DocumentAuditPipeline


def example_1_basic_usage():
    """示例 1: 基本使用"""
    print("=" * 70)
    print("示例 1: 基本使用")
    print("=" * 70)
    
    # 创建 Pipeline
    pipeline = DocumentAuditPipeline()
    
    # 审核作业指导书
    report = pipeline.run_sync(
        document_path="examples/sample_work_instruction.pdf",
        scenario_id="work_instruction_audit"
    )
    
    print(f"最终得分: {report.audit_result.final_score}/100")
    print(f"发现问题: {len(report.audit_result.violations)} 个")
    print(f"审核结果: {'通过' if report.audit_result.passed else '不通过'}")


def example_2_risk_management():
    """示例 2: 风险管控方案审核"""
    print("\n" + "=" * 70)
    print("示例 2: 风险管控方案审核")
    print("=" * 70)
    
    pipeline = DocumentAuditPipeline()
    
    # 审核风险管控方案
    report = pipeline.run_sync(
        document_path="examples/sample_risk_plan.docx",
        scenario_id="risk_management_audit",
        output_name="risk_audit"
    )
    
    print(f"最终得分: {report.audit_result.final_score}/100")
    print(f"带批注文档: {report.annotated_document_path}")
    print(f"审核报告: {report.report_path}")


def example_3_custom_config():
    """示例 3: 使用自定义配置"""
    print("\n" + "=" * 70)
    print("示例 3: 使用自定义配置")
    print("=" * 70)
    
    # 使用自定义配置文件
    pipeline = DocumentAuditPipeline(config_path="config/config.yaml")
    
    report = pipeline.run_sync(
        document_path="examples/sample_document.pdf",
        scenario_id="work_instruction_audit"
    )
    
    print(f"处理时间: {report.processing_time:.2f} 秒")
    print(f"审核人: {report.auditor}")


def example_4_async_usage():
    """示例 4: 异步使用"""
    print("\n" + "=" * 70)
    print("示例 4: 异步使用")
    print("=" * 70)
    
    import asyncio
    
    async def audit_multiple_documents():
        pipeline = DocumentAuditPipeline()
        
        # 并发审核多个文档
        tasks = [
            pipeline.process_document(
                "examples/doc1.pdf",
                "work_instruction_audit"
            ),
            pipeline.process_document(
                "examples/doc2.pdf",
                "risk_management_audit"
            )
        ]
        
        reports = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, report in enumerate(reports):
            if isinstance(report, Exception):
                print(f"文档 {i+1} 审核失败: {report}")
            else:
                print(f"文档 {i+1} 得分: {report.audit_result.final_score}/100")
    
    # 运行异步任务
    asyncio.run(audit_multiple_documents())


def example_5_error_handling():
    """示例 5: 错误处理"""
    print("\n" + "=" * 70)
    print("示例 5: 错误处理")
    print("=" * 70)
    
    pipeline = DocumentAuditPipeline()
    
    try:
        report = pipeline.run_sync(
            document_path="examples/sample_document.pdf",
            scenario_id="work_instruction_audit"
        )
        print("审核成功！")
        
    except FileNotFoundError as e:
        print(f"文件不存在: {e}")
    except ValueError as e:
        print(f"参数错误: {e}")
    except asyncio.TimeoutError:
        print("处理超时（超过 120 秒）")
    except Exception as e:
        print(f"审核失败: {e}")


if __name__ == '__main__':
    print("文档智能审核系统 - 使用示例\n")
    
    # 运行示例
    # example_1_basic_usage()
    # example_2_risk_management()
    # example_3_custom_config()
    # example_4_async_usage()
    # example_5_error_handling()
    
    print("\n取消注释上面的函数调用来运行具体示例")

