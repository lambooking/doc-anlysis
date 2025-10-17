#!/usr/bin/env python3
"""
扣分优化脚本 - 降低审核规则的扣分严格程度

该脚本会:
1. 读取原配置文件 config/audit_rules.yaml
2. 按照严重程度调整扣分值
3. 生成优化后的配置文件 config/audit_rules_optimized.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, Any


# ============ 配置参数 ============
# 降低比例（可根据需要调整）
REDUCTION_FACTOR = 0.4  # 降低到原来的40%

# 严重程度对应的降低比例（可以差异化调整）
SEVERITY_REDUCTION = {
    'critical': 0.5,  # 关键问题保持50%扣分
    'high': 0.4,      # 高优先级40%
    'medium': 0.3,    # 中优先级30%
    'low': 0.2        # 低优先级20%
}

# 最小扣分值（避免扣分过低）
MIN_DEDUCTION = {
    'critical': 3,
    'high': 2,
    'medium': 1,
    'low': 1
}


def reduce_deductions(config: Dict[str, Any]) -> Dict[str, Any]:
    """降低配置中的所有扣分值"""
    
    modified_count = 0
    
    for scenario in config.get('audit_scenarios', []):
        for dimension in scenario.get('dimensions', []):
            for item in dimension.get('items', []):
                for checkpoint in item.get('checkpoints', []):
                    
                    severity = checkpoint.get('severity', 'medium')
                    old_deduction = checkpoint.get('max_deduction', 0)
                    
                    # 根据严重程度计算新扣分
                    reduction_ratio = SEVERITY_REDUCTION.get(severity, REDUCTION_FACTOR)
                    new_deduction = int(old_deduction * reduction_ratio)
                    
                    # 应用最小扣分限制
                    min_deduction = MIN_DEDUCTION.get(severity, 1)
                    new_deduction = max(new_deduction, min_deduction)
                    
                    # 更新扣分值
                    if new_deduction != old_deduction:
                        checkpoint['max_deduction'] = new_deduction
                        modified_count += 1
                        
                        print(f"[{severity.upper():8s}] {checkpoint['checkpoint_id']:20s} "
                              f"{old_deduction:3d} → {new_deduction:3d} 分")
    
    print(f"\n✅ 共修改 {modified_count} 项扣分规则")
    
    return config


def main():
    """主函数"""
    
    # 确定项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    input_file = project_root / "config" / "audit_rules.yaml"
    output_file = project_root / "config" / "audit_rules_optimized.yaml"
    
    # 检查输入文件
    if not input_file.exists():
        print(f"❌ 错误: 找不到配置文件 {input_file}")
        return 1
    
    print(f"📖 读取配置文件: {input_file}")
    
    # 读取原配置
    with open(input_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    print(f"✅ 配置文件加载成功\n")
    print("=" * 70)
    print("开始调整扣分值...")
    print("=" * 70)
    
    # 调整扣分
    optimized_config = reduce_deductions(config)
    
    # 保存优化后的配置
    print(f"\n💾 保存优化配置到: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(optimized_config, f, 
                  allow_unicode=True, 
                  sort_keys=False,
                  default_flow_style=False,
                  indent=2)
    
    print(f"✅ 优化配置已保存\n")
    print("=" * 70)
    print("📋 后续操作建议:")
    print("=" * 70)
    print("1. 查看生成的文件确认调整是否合理:")
    print(f"   {output_file}")
    print("")
    print("2. 如果满意,备份原文件并替换:")
    print(f"   cp {input_file} {input_file.parent}/audit_rules_backup.yaml")
    print(f"   cp {output_file} {input_file}")
    print("")
    print("3. 如果觉得扣分还是太多/太少,可以修改脚本中的参数:")
    print(f"   - REDUCTION_FACTOR: 当前为 {REDUCTION_FACTOR}")
    print(f"   - SEVERITY_REDUCTION: 差异化调整不同严重程度")
    print("")
    print("4. 测试验证:")
    print("   python main.py --input test.docx --scenario work_instruction_audit")
    
    return 0


if __name__ == "__main__":
    exit(main())

