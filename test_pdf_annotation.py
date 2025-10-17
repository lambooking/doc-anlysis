#!/usr/bin/env python3
"""测试 PyMuPDF 批注写入"""

import pymupdf
from pathlib import Path

# 创建一个简单的测试 PDF
output_dir = Path("temp")
output_dir.mkdir(exist_ok=True)

# 创建测试PDF
doc = pymupdf.open()
page = doc.new_page()

# 添加一些文本
page.insert_text((50, 50), "测试文本内容", fontsize=12)

# 测试1: 使用 set_info 方法
rect1 = pymupdf.Rect(50, 50, 150, 70)
highlight1 = page.add_highlight_annot(rect1)
highlight1.set_colors(stroke=(1, 1, 0))

title1 = "测试标题1 - 使用set_info"
content1 = "问题: 这是测试问题\n\n级别: 高优先级\n\n扣分: 2分\n\n建议: 请修改\n\n规则: test_01"

print("=" * 60)
print("测试1: 使用 set_info 方法")
print(f"标题: {repr(title1)}")
print(f"内容: {repr(content1)}")

highlight1.set_info(title=title1, content=content1)
highlight1.update()

# 测试2: 直接设置属性
page.insert_text((50, 100), "测试文本内容2", fontsize=12)
rect2 = pymupdf.Rect(50, 100, 150, 120)
highlight2 = page.add_highlight_annot(rect2)
highlight2.set_colors(stroke=(1, 0.5, 0))

title2 = "测试标题2 - 直接设置属性"
content2 = "问题: 这是测试问题2\n\n级别: 中优先级\n\n扣分: 1分"

print("\n测试2: 直接设置属性")
print(f"标题: {repr(title2)}")
print(f"内容: {repr(content2)}")

highlight2.info["title"] = title2
highlight2.info["content"] = content2
highlight2.update()

# 测试3: 使用 set_info 但分开调用
page.insert_text((50, 150), "测试文本内容3", fontsize=12)
rect3 = pymupdf.Rect(50, 150, 150, 170)
highlight3 = page.add_highlight_annot(rect3)
highlight3.set_colors(stroke=(1, 0, 0))

title3 = "测试标题3 - 分开设置"
content3 = "这是内容测试\n包含多行\n测试换行符"

print("\n测试3: 分开设置")
print(f"标题: {repr(title3)}")
print(f"内容: {repr(content3)}")

highlight3.set_info(title=title3)
highlight3.set_info(content=content3)
highlight3.update()

# 保存
output_file = output_dir / "test_annotation.pdf"
doc.save(str(output_file))
doc.close()

print(f"\n✓ 测试PDF已生成: {output_file}")
print("=" * 60)

# 读回并验证
print("\n验证批注内容...")
doc2 = pymupdf.open(str(output_file))
page2 = doc2[0]
annots = page2.annots()

if annots:
    for i, annot in enumerate(annots):
        print(f"\n批注 {i+1}:")
        print(f"  类型: {annot.type}")
        info = annot.info
        print(f"  标题: {repr(info.get('title', 'N/A'))}")
        print(f"  内容: {repr(info.get('content', 'N/A'))}")
else:
    print("❌ 没有找到批注")

doc2.close()
print("\n" + "=" * 60)

