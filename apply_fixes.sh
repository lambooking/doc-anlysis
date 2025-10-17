#!/bin/bash
# 应用所有修复的脚本

echo "=============================================="
echo "   审核系统修复应用脚本"
echo "=============================================="
echo ""

# 切换到项目根目录
cd "$(dirname "$0")"

echo "📍 当前目录: $(pwd)"
echo ""

# 步骤1：备份原配置
echo "步骤 1/3: 备份原配置文件..."
BACKUP_FILE="config/audit_rules_backup_$(date +%Y%m%d_%H%M%S).yaml"
if [ -f "config/audit_rules.yaml" ]; then
    cp config/audit_rules.yaml "$BACKUP_FILE"
    echo "✓ 已备份到: $BACKUP_FILE"
else
    echo "⚠️  原配置文件不存在"
fi
echo ""

# 步骤2：运行扣分修复脚本
echo "步骤 2/3: 运行扣分修复脚本..."
if [ -f "tools/emergency_fix_deductions.py" ]; then
    python tools/emergency_fix_deductions.py
    echo ""
    
    # 应用修复后的配置
    if [ -f "config/audit_rules_emergency_fix.yaml" ]; then
        cp config/audit_rules_emergency_fix.yaml config/audit_rules.yaml
        echo "✓ 已应用新的扣分配置"
    else
        echo "❌ 未找到修复后的配置文件"
        exit 1
    fi
else
    echo "❌ 未找到修复脚本: tools/emergency_fix_deductions.py"
    exit 1
fi
echo ""

# 步骤3：总结
echo "步骤 3/3: 修复总结"
echo "=============================================="
echo "✅ 所有修复已应用！"
echo ""
echo "已完成的修复："
echo "  1. ✓ 扣分规则已降低（critical: 2分, high: 1.5分, medium: 1分, low: 0.5分）"
echo "  2. ✓ VLM Prompt 已增强（要求严格的 text_snippet）"
echo "  3. ✓ violation 清洗验证已加强（过滤无效问题）"
echo "  4. ✓ 扣分上限保护已添加（最多80分）"
echo "  5. ✓ 批注标题格式已优化"
echo ""
echo "预期改进效果："
echo "  • 总扣分：从 998分 → 30-50分"
echo "  • 最终得分：从 0分 → 50-70分"
echo "  • 批注定位成功率：从 18% → 75%+"
echo ""
echo "下一步："
echo "  运行测试: python main.py --input <文档路径> --scenario work_instruction_audit"
echo "=============================================="

