"""从竞赛规则PDF抽取评分细则并写回 config/audit_rules.yaml。

用法:
  python tools/import_rules_from_pdf.py \
    --pdf "./生产运维管理领域AI 算法应用竞赛规则-2025.7.11最终版_副本2.pdf" \
    --scenario work_instruction_audit \
    --write

说明:
- 若PDF中未给出明确权重/分值，自动按“平均归一”策略为各维度/检查点分配权重与最大扣分，
  并将场景总分定为100分（两个场景相互独立）。
- 本脚本为启发式实现，优先抽取包含“必须/应/不得/严禁/需要/包含”等关键词的句子作为检查点。
  可反复运行以覆盖旧规则。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

try:
    import pymupdf4llm  # type: ignore
    import pymupdf  # type: ignore
except Exception:
    pymupdf4llm = None
    pymupdf = None


def pdf_to_markdown(pdf_path: Path) -> str:
    """优先用pymupdf4llm转Markdown，失败则退化为纯文本。"""
    if pymupdf4llm is not None:
        try:
            md = pymupdf4llm.to_markdown(doc=str(pdf_path), page_chunks=False)
            return md if isinstance(md, str) else json.dumps(md, ensure_ascii=False)
        except Exception:
            pass

    if pymupdf is not None:
        try:
            doc = pymupdf.open(str(pdf_path))
            parts = []
            for i, page in enumerate(doc):
                parts.append(f"\n\n--- 第 {i+1} 页 ---\n\n")
                parts.append(page.get_text())
            doc.close()
            return "".join(parts)
        except Exception:
            pass

    raise RuntimeError("无法解析PDF，请确保已安装 PyMuPDF/pymupdf4llm")


def split_sections(md: str) -> List[str]:
    """粗分段：按行，将明显的条目/标题聚合为句子级别列表。"""
    lines = [l.strip() for l in md.splitlines()]
    sections: List[str] = []
    buf: List[str] = []
    for line in lines:
        if not line:
            if buf:
                sections.append(" ".join(buf).strip())
                buf = []
            continue
        # 遇到大标题/编号时，切段
        if line.startswith(('#', '##', '###')) or any(
            line.startswith(p) for p in (
                '一、', '二、', '三、', '四、', '五、', '六、', '七、', '八、', '九、',
                '（一）', '（二）', '（三）', '（四）', '（五）',
                '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.',
                '1、', '2、', '3、', '4、', '5、', '6、'
            )
        ):
            if buf:
                sections.append(" ".join(buf).strip())
                buf = []
        buf.append(line)
    if buf:
        sections.append(" ".join(buf).strip())
    return [s for s in sections if s]


KEYWORDS_CRITICAL = ("必须", "严禁", "不得", "一票否决")
KEYWORDS_HIGH = ("应当", "应", "需要")
KEYWORDS_MEDIUM = ("建议", "可", "鼓励")


def classify_severity(text: str) -> str:
    t = text
    if any(k in t for k in KEYWORDS_CRITICAL):
        return "critical"
    if any(k in t for k in KEYWORDS_HIGH):
        return "high"
    if any(k in t for k in KEYWORDS_MEDIUM):
        return "medium"
    return "medium"


def extract_checkpoints(md: str, scenario_id: str) -> List[Dict]:
    """从Markdown中抽取候选检查点。"""
    sections = split_sections(md)
    checkpoints: List[Dict] = []

    # 场景特定过滤关键词，尽量聚焦
    if "work_instruction" in scenario_id:
        focus_words = (
            "目录", "编号", "职责", "流程", "操作", "应急", "培训", "风险", "QHSE",
            "语句", "标点", "术语", "逻辑", "一致", "图片", "表格"
        )
    else:
        focus_words = (
            "路线", "图例", "标注", "半径", "疏散", "入场", "签字", "日期", "签名",
            "建筑物", "风险等级", "电位", "影响范围"
        )

    for sec in sections:
        if not any(w in sec for w in focus_words):
            continue
        # 拆分成短句
        parts = [p.strip() for p in sec.replace('；', '。').replace(';', '。').split('。') if p.strip()]
        for sent in parts:
            if len(sent) < 6:
                continue
            if any(k in sent for k in KEYWORDS_CRITICAL + KEYWORDS_HIGH + KEYWORDS_MEDIUM):
                cp_id = slugify_checkpoint(sent)[:24] or "cp"
                checkpoints.append({
                    "checkpoint_id": cp_id,
                    "description": sent,
                    "severity": classify_severity(sent),
                    # max_deduction 占位，稍后按“平均归一”计算
                    "max_deduction": 0,
                })

    # 去重（按description）
    uniq = []
    seen = set()
    for cp in checkpoints:
        key = cp["description"]
        if key not in seen:
            uniq.append(cp)
            seen.add(key)
    return uniq


def slugify_checkpoint(text: str) -> str:
    allowed = ''.join(ch for ch in text if ('0' <= ch <= '9') or ('a' <= ch.lower() <= 'z'))
    if not allowed:
        # 回退：用拼音不可行，这里简单用hash
        import hashlib
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    return allowed.lower()


def average_assign(scenario_id: str, checkpoints: List[Dict]) -> Dict:
    """将检查点按“平均归一”策略装配成一个场景配置。

    策略：
    - 设单一维度 `content_audit` 权重为1.0；
    - 所有检查点分到一个 `content_quality` 审核项下；
    - 场景总分100，按检查点数量均分为 max_deduction，末项承接余数；
    - 若数量很少，最小扣分设为1。
    """
    total_points = 100
    n = max(1, len(checkpoints))
    base = total_points // n
    remainder = total_points - base * n
    if base < 1:
        base = 1

    for i, cp in enumerate(checkpoints):
        cp["max_deduction"] = base + (1 if i < remainder else 0)

    scenario = {
        "scenario_id": scenario_id,
        "name": "作业指导书审核" if "work_instruction" in scenario_id else "风险管控方案审核",
        "total_points": total_points,
        "dimensions": [
            {
                "dimension_id": "content_audit",
                "name": "内容审核",
                "weight": 1.0,
                "items": [
                    {
                        "item_id": "content_quality",
                        "name": "内容质量与合规性",
                        "checkpoints": checkpoints or [
                            {
                                "checkpoint_id": "cp_default",
                                "description": "内容完整性与规范性检查",
                                "severity": "medium",
                                "max_deduction": 100,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    return scenario


def load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {"version": "1.0", "audit_scenarios": []}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {"version": "1.0", "audit_scenarios": []}


def upsert_scenario(data: Dict, scenario: Dict, source_pdf: Path) -> Dict:
    data = dict(data)
    data.setdefault("version", "1.0")
    data.setdefault("audit_scenarios", [])
    data["source_pdf"] = str(source_pdf.name)
    data["generated_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    updated = False
    for i, sc in enumerate(data["audit_scenarios"]):
        if sc.get("scenario_id") == scenario.get("scenario_id"):
            data["audit_scenarios"][i] = scenario
            updated = True
            break
    if not updated:
        data["audit_scenarios"].append(scenario)
    return data


def save_yaml(path: Path, data: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="从竞赛PDF抽取评分细则并更新audit_rules.yaml")
    parser.add_argument('--pdf', required=True, help='竞赛规则PDF路径')
    parser.add_argument('--scenario', required=True, choices=['work_instruction_audit', 'risk_management_audit'])
    parser.add_argument('--write', action='store_true', help='写回配置文件')
    parser.add_argument('--out', default='config/audit_rules.yaml', help='配置文件输出路径')
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF不存在: {pdf_path}")

    md = pdf_to_markdown(pdf_path)
    checkpoints = extract_checkpoints(md, args.scenario)
    scenario_cfg = average_assign(args.scenario, checkpoints)

    if not args.write:
        print(json.dumps({"scenario": scenario_cfg}, ensure_ascii=False, indent=2))
        return

    # 合入现有YAML
    yaml_path = Path(args.out)
    data = load_yaml(yaml_path)
    data = upsert_scenario(data, scenario_cfg, pdf_path)
    save_yaml(yaml_path, data)

    print(f"规则已更新: {yaml_path}")


if __name__ == '__main__':
    main()


