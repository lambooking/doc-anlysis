#!/usr/bin/env python3
"""调试 PDF 批注写入"""

import sys
from pathlib import Path

# 让用户提供 PDF 路径
if len(sys.argv) < 2:
    print("用法: python debug_pdf_annotation.py <PDF文件路径>")
    sys.exit(1)

pdf_path = sys.argv[1]

try:
    import pymupdf
    
    print("=" * 60)
    print(f"检查 PDF 批注: {pdf_path}")
    print("=" * 60)
    
    doc = pymupdf.open(pdf_path)
    
    total_annots = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        annots = list(page.annots())
        
        if annots:
            print(f"\n第 {page_num + 1} 页: 找到 {len(annots)} 个批注")
            
            for i, annot in enumerate(annots):
                total_annots += 1
                print(f"\n  批注 {i+1}:")
                print(f"    类型: {annot.type}")
                
                info = annot.info
                print(f"    标题 (title): {repr(info.get('title', 'N/A'))}")
                print(f"    内容 (content): {repr(info.get('content', 'N/A'))}")
                print(f"    主题 (subject): {repr(info.get('subject', 'N/A'))}")
                
                # 显示前100个字符的内容
                content = info.get('content', '')
                if content and len(content) > 100:
                    print(f"    内容预览: {content[:100]}...")
                elif content:
                    print(f"    完整内容: {content}")
                else:
                    print(f"    ⚠️  内容为空！")
    
    doc.close()
    
    print("\n" + "=" * 60)
    print(f"总共找到 {total_annots} 个批注")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

