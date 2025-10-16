"""基础测试"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试导入"""
    print("测试导入模块...")
    
    try:
        from src.core.document_processor import DocumentProcessor
        print("✓ DocumentProcessor")
        
        from src.core.vlm_client import VLMClient
        print("✓ VLMClient")
        
        from src.core.annotator import PDFAnnotator, DocumentAnnotator
        print("✓ Annotator")
        
        from src.core.report_generator import ReportGenerator
        print("✓ ReportGenerator")
        
        from src.pipeline import DocumentAuditPipeline
        print("✓ Pipeline")
        
        from src.models.schemas import AuditResult, Violation
        print("✓ Schemas")
        
        from src.models.rule_engine import RuleEngine
        print("✓ RuleEngine")
        
        from src.utils.config import get_config
        print("✓ Config")
        
        from src.utils.logger import get_logger
        print("✓ Logger")
        
        print("\n✓ 所有模块导入成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """测试配置"""
    print("\n测试配置...")
    
    try:
        from src.utils.config import get_config
        
        config = get_config()
        
        print(f"✓ vLLM URL: {config.vllm_base_url}")
        print(f"✓ 模型: {config.vllm_model}")
        print(f"✓ 超时: {config.pipeline_timeout}s")
        print(f"✓ DPI: {config.pipeline_dpi}")
        print(f"✓ 输出目录: {config.output_dir}")
        
        print("\n✓ 配置加载成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rule_engine():
    """测试规则引擎"""
    print("\n测试规则引擎...")
    
    try:
        from src.models.rule_engine import RuleEngine
        
        engine = RuleEngine()
        
        # 测试场景加载
        scenario_ids = engine.get_all_scenario_ids()
        print(f"✓ 加载场景: {scenario_ids}")
        
        # 测试规则格式化
        for sid in scenario_ids:
            scenario = engine.get_scenario(sid)
            print(f"✓ 场景 '{scenario.name}' 包含 {len(scenario.dimensions)} 个维度")
            
            rules_text = engine.format_rules_for_prompt(sid)
            print(f"  - 格式化规则长度: {len(rules_text)} 字符")
        
        print("\n✓ 规则引擎测试成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 规则引擎测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_models():
    """测试数据模型"""
    print("\n测试数据模型...")
    
    try:
        from src.models.schemas import (
            AuditResult, Violation, LocationEncoding,
            Checkpoint, AuditItem, AuditDimension
        )
        
        # 创建测试数据
        location = LocationEncoding(
            page=1,
            text_snippet="这是一个测试文本片段用于定位问题位置",
            region_description="第一章 引言"
        )
        
        violation = Violation(
            rule_id="test_01",
            severity="high",
            location=location,
            finding="这是一个测试问题",
            points_deducted=5
        )
        
        result = AuditResult(
            violations=[violation],
            total_deductions=5,
            final_score=95,
            passed=True
        )
        
        print(f"✓ 创建测试违规: {violation.rule_id}")
        print(f"✓ 创建测试结果: {result.final_score}/100")
        
        # 测试 JSON 序列化
        json_str = result.model_dump_json()
        print(f"✓ JSON 序列化长度: {len(json_str)} 字符")
        
        # 测试 JSON 反序列化
        result2 = AuditResult.model_validate_json(json_str)
        print(f"✓ JSON 反序列化: {result2.final_score}/100")
        
        print("\n✓ 数据模型测试成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 数据模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_directory_structure():
    """测试目录结构"""
    print("\n测试目录结构...")
    
    try:
        required_dirs = [
            'src/core',
            'src/models',
            'src/utils',
            'config',
            'temp',
            'output',
            'logs'
        ]
        
        for dir_path in required_dirs:
            path = project_root / dir_path
            if path.exists():
                print(f"✓ {dir_path}/")
            else:
                print(f"✗ {dir_path}/ (不存在)")
                path.mkdir(parents=True, exist_ok=True)
                print(f"  → 已创建")
        
        required_files = [
            'config/config.yaml',
            'config/audit_rules.yaml',
            'requirements.txt',
            'main.py'
        ]
        
        for file_path in required_files:
            path = project_root / file_path
            if path.exists():
                print(f"✓ {file_path}")
            else:
                print(f"✗ {file_path} (不存在)")
        
        print("\n✓ 目录结构检查完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 目录结构检查失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 70)
    print("文档智能审核系统 - 基础测试")
    print("=" * 70)
    
    tests = [
        ("导入测试", test_imports),
        ("配置测试", test_config),
        ("规则引擎测试", test_rule_engine),
        ("数据模型测试", test_data_models),
        ("目录结构测试", test_directory_structure),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} 异常: {e}")
            results.append((name, False))
    
    # 汇总
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统就绪。")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查配置。")
        return 1


if __name__ == '__main__':
    sys.exit(main())

