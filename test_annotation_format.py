#!/usr/bin/env python3
"""测试批注内容格式化"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.models.schemas import Violation, LocationEncoding
from src.core.annotator import PDFAnnotator

# 创建测试用例
violation = Violation(
    rule_id="term_02",
    severity="high",
    finding="标题层级不连续: 3.2 → 3.4，缺少3.3",
    location=LocationEncoding(
        page=23,
        text_snippet="4.3 安全管理",
        region_description="目录章节标题"
    ),
    points_deducted=2
)

# 测试格式化
annotator = PDFAnnotator()

title = annotator._format_annotation_title(violation, 50)
content = annotator._format_annotation_content(violation, 50)

print("=" * 60)
print("测试批注格式化")
print("=" * 60)
print(f"\n【标题】")
print(repr(title))
print(f"\n实际显示: {title}")
print(f"\n【内容】")
print(repr(content))
print(f"\n实际显示:")
print(content)
print("\n" + "=" * 60)

# 检查是否包含特殊字符
special_chars = ['"""', "'''", "【", "】", "🔴", "🟠", "🟡", "🟢", "💡"]
found_special = []
for char in special_chars:
    if char in content or char in title:
        found_special.append(char)

if found_special:
    print(f"\n⚠️  警告：发现特殊字符: {found_special}")
else:
    print(f"\n✓ 没有发现特殊字符")

