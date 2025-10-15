#!/bin/bash
# 快速启动脚本

echo "文档智能审核系统 - 快速启动"
echo "=============================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python 3"
    exit 1
fi

echo "✓ Python 版本: $(python3 --version)"

# 检查依赖
echo ""
echo "检查依赖..."
if ! python3 -c "import pymupdf" 2>/dev/null; then
    echo "✗ 依赖未安装，正在安装..."
    pip install -r requirements.txt
else
    echo "✓ 依赖已安装"
fi

# 创建必要目录
echo ""
echo "创建目录..."
mkdir -p temp output logs
echo "✓ 目录创建完成"

# 检查配置
echo ""
if [ ! -f "config/config.yaml" ]; then
    echo "✗ 配置文件不存在: config/config.yaml"
    exit 1
else
    echo "✓ 配置文件存在"
fi

if [ ! -f "config/audit_rules.yaml" ]; then
    echo "✗ 规则文件不存在: config/audit_rules.yaml"
    exit 1
else
    echo "✓ 规则文件存在"
fi

# 显示使用说明
echo ""
echo "=============================="
echo "系统就绪！"
echo "=============================="
echo ""
echo "使用方法:"
echo ""
echo "1. 审核作业指导书:"
echo "   python main.py your_document.pdf --scenario work_instruction_audit"
echo ""
echo "2. 审核风险管控方案:"
echo "   python main.py your_document.docx --scenario risk_management_audit"
echo ""
echo "3. 查看帮助:"
echo "   python main.py --help"
echo ""
echo "输出文件位置: ./output/"
echo ""

