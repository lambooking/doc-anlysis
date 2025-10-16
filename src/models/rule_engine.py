"""规则引擎模块"""
import yaml
from pathlib import Path
from typing import Optional
from .schemas import AuditRuleConfig, AuditScenario


class RuleEngine:
    """规则引擎"""
    
    def __init__(self, rule_file: str = "config/audit_rules.yaml"):
        self.rule_file = Path(rule_file)
        self.config: Optional[AuditRuleConfig] = None
        self.load_rules()
    
    def load_rules(self):
        """加载审核规则"""
        if not self.rule_file.exists():
            raise FileNotFoundError(f"规则文件不存在: {self.rule_file}")
        
        with open(self.rule_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.config = AuditRuleConfig(**data)
    
    def get_scenario(self, scenario_id: str) -> Optional[AuditScenario]:
        """获取指定场景的规则"""
        if not self.config:
            return None
        
        for scenario in self.config.audit_scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        
        return None
    
    def format_rules_for_prompt(self, scenario_id: str) -> str:
        """将规则格式化为 Prompt 文本"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"场景不存在: {scenario_id}")
        
        output = []
        output.append(f"# {scenario.name}\n")
        output.append(f"总分: {scenario.total_points} 分\n")
        
        for dimension in scenario.dimensions:
            output.append(f"\n## {dimension.name} (权重: {dimension.weight:.0%})\n")
            
            for item in dimension.items:
                output.append(f"\n### {item.name}\n")
                
                for cp in item.checkpoints:
                    output.append(f"**[{cp.checkpoint_id}]** {cp.description}\n")
                    output.append(f"- 严重程度: {cp.severity}\n")
                    output.append(f"- 最大扣分: {cp.max_deduction} 分\n")
        
        return "\n".join(output)
    
    def get_all_scenario_ids(self) -> list:
        """获取所有场景 ID"""
        if not self.config:
            return []
        return [scenario.scenario_id for scenario in self.config.audit_scenarios]

