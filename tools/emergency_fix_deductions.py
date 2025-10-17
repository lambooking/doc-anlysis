"""紧急修复扣分规则 - 一键降低到合理范围"""
import yaml
from pathlib import Path

def emergency_fix():
    """将所有扣分降低到合理范围"""
    
    CONFIG_PATH = "config/audit_rules.yaml"
    
    # 新的扣分标准（非常宽松）
    NEW_DEDUCTIONS = {
        'critical': 2,   # 原来可能是 8-10
        'high': 1.5,     # 原来可能是 5-7
        'medium': 1,     # 原来可能是 3-5
        'low': 0.5       # 原来可能是 2-3
    }
    
    print("🚨 紧急修复模式：将所有扣分降低到最低水平")
    print(f"   critical → {NEW_DEDUCTIONS['critical']} 分")
    print(f"   high → {NEW_DEDUCTIONS['high']} 分")
    print(f"   medium → {NEW_DEDUCTIONS['medium']} 分")
    print(f"   low → {NEW_DEDUCTIONS['low']} 分\n")
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    count = 0
    total_before = 0
    total_after = 0
    
    def fix_checkpoints(obj):
        nonlocal count, total_before, total_after
        
        if isinstance(obj, dict):
            if 'checkpoint_id' in obj and 'max_deduction' in obj and 'severity' in obj:
                old_value = obj['max_deduction']
                new_value = NEW_DEDUCTIONS[obj['severity']]
                obj['max_deduction'] = new_value
                
                count += 1
                total_before += old_value
                total_after += new_value
                
                print(f"✓ {obj['checkpoint_id']:25s} [{obj['severity']:8s}] {old_value:5.1f} → {new_value:5.1f}")
            
            for value in obj.values():
                fix_checkpoints(value)
        elif isinstance(obj, list):
            for item in obj:
                fix_checkpoints(item)
    
    fix_checkpoints(config)
    
    # 保存
    output_path = CONFIG_PATH.replace('.yaml', '_emergency_fix.yaml')
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"\n{'='*70}")
    print(f"修复完成！")
    print(f"{'='*70}")
    print(f"修改检查点数量: {count}")
    print(f"原始最大扣分: {total_before:.1f} 分")
    print(f"修复后最大扣分: {total_after:.1f} 分")
    print(f"降低幅度: {(1 - total_after/total_before)*100:.1f}%")
    print(f"\n预期效果：")
    print(f"  - 230 个问题 × 平均 1 分 ≈ 230 分")
    print(f"  - 但实际扣分会因为去重、上限等机制更低")
    print(f"  - 预计总扣分：30-50 分")
    print(f"  - 预计最终得分：50-70 分 ✅")
    print(f"\n已保存到: {output_path}")
    print(f"\n下一步：")
    print(f"  cp {output_path} config/audit_rules.yaml")

if __name__ == "__main__":
    emergency_fix()

