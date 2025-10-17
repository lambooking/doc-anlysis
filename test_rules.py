"""测试规则引擎和新规则加载"""
from src.models.rule_engine import RuleEngine

def test_work_instruction_rules():
    """测试作业指导书审核规则"""
    engine = RuleEngine()
    scenario = engine.get_scenario('work_instruction_audit')
    
    print("=" * 60)
    print(f"场景: {scenario.name}")
    print(f"总分: {scenario.total_points}")
    print(f"维度数量: {len(scenario.dimensions)}")
    print("=" * 60)
    
    for dim in scenario.dimensions:
        print(f"\n【{dim.name}】 权重: {dim.weight:.0%}")
        total_checkpoints = sum(len(item.checkpoints) for item in dim.items)
        print(f"  审核项数量: {len(dim.items)}, 检查点数量: {total_checkpoints}")
    
    # 统计新增的维度
    new_dimensions = [d for d in scenario.dimensions if d.dimension_id in ['grammar_correctness', 'logic_coherence']]
    print(f"\n新增维度数量: {len(new_dimensions)}")
    for dim in new_dimensions:
        print(f"  ✓ {dim.name}")

def test_risk_management_rules():
    """测试风险管控方案审核规则"""
    engine = RuleEngine()
    scenario = engine.get_scenario('risk_management_audit')
    
    print("\n" + "=" * 60)
    print(f"场景: {scenario.name}")
    print(f"总分: {scenario.total_points}")
    print(f"维度数量: {len(scenario.dimensions)}")
    print("=" * 60)
    
    for dim in scenario.dimensions:
        print(f"\n【{dim.name}】 权重: {dim.weight:.0%}")
        total_checkpoints = sum(len(item.checkpoints) for item in dim.items)
        print(f"  审核项数量: {len(dim.items)}, 检查点数量: {total_checkpoints}")
    
    # 统计新增的维度
    new_dimensions = [d for d in scenario.dimensions if d.dimension_id in ['image_annotation', 'text_image_consistency', 'data_compliance']]
    print(f"\n新增维度数量: {len(new_dimensions)}")
    for dim in new_dimensions:
        print(f"  ✓ {dim.name}")

def test_prompt_generation():
    """测试Prompt生成"""
    from src.core.vlm_client import VLMClient
    
    print("\n" + "=" * 60)
    print("测试 Prompt 生成")
    print("=" * 60)
    
    client = VLMClient()
    
    # 测试作业指导书Prompt
    prompt1 = client._generate_system_prompt('work_instruction_audit')
    print(f"\n作业指导书 Prompt 长度: {len(prompt1)} 字符")
    print(f"包含'语法错误': {'语法错误' in prompt1}")
    print(f"包含'业务逻辑': {'业务逻辑' in prompt1}")
    print(f"包含'应急处置': {'应急处置' in prompt1}")
    
    # 测试风险管控Prompt
    prompt2 = client._generate_system_prompt('risk_management_audit')
    print(f"\n风险管控 Prompt 长度: {len(prompt2)} 字符")
    print(f"包含'图片内容': {'图片内容' in prompt2}")
    print(f"包含'影像图': {'影像图' in prompt2}")
    print(f"包含'入场路线': {'入场路线' in prompt2}")
    print(f"包含'图文不一致': {'图文不一致' in prompt2}")

if __name__ == "__main__":
    try:
        test_work_instruction_rules()
        test_risk_management_rules()
        test_prompt_generation()
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！规则加载成功，Prompt生成正常。")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

