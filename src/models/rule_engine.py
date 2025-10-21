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
        # 构建索引便于计分
        self._build_index()
    
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

    # ==================== 计分辅助（新增） ====================
    def _build_index(self):
        """根据规则配置构建快速索引。"""
        self._checkpoint_index = {}  # (scenario_id, checkpoint_id) -> dict
        self._dimension_index = {}   # (scenario_id, dimension_id) -> dimension
        if not self.config:
            return
        for scenario in self.config.audit_scenarios:
            for dim in scenario.dimensions:
                self._dimension_index[(scenario.scenario_id, dim.dimension_id)] = dim
                for item in dim.items:
                    for cp in item.checkpoints:
                        self._checkpoint_index[(scenario.scenario_id, cp.checkpoint_id)] = {
                            'scenario_id': scenario.scenario_id,
                            'scenario_total_points': scenario.total_points,
                            'dimension_id': dim.dimension_id,
                            'dimension_weight': dim.weight,
                            'item_id': item.item_id,
                            'checkpoint': cp,
                        }

    def get_checkpoint_info(self, scenario_id: str, checkpoint_id: str):
        """返回检查点信息与所在维度权重。
        返回 None 表示在规则中未定义该检查点。
        """
        if not hasattr(self, '_checkpoint_index'):
            self._build_index()
        return self._checkpoint_index.get((scenario_id, checkpoint_id))

    def get_dimension_max_points(self, scenario_id: str, dimension_id: str) -> int:
        """返回某维度的满分（权重×场景总分，取整）。"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return 0
        dim = None
        for d in scenario.dimensions:
            if d.dimension_id == dimension_id:
                dim = d
                break
        if not dim:
            return 0
        return int(round(scenario.total_points * dim.weight))

