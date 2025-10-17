"""配置管理模块"""
import yaml
from pathlib import Path
from typing import Any, Dict


class Config:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self):
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点分隔的嵌套键"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    @property
    def vllm_base_url(self) -> str:
        return self.get('vllm.base_url', 'http://localhost:8000/v1')
    
    @property
    def vllm_api_key(self) -> str:
        return self.get('vllm.api_key', 'token-abc123')
    
    @property
    def vllm_model(self) -> str:
        return self.get('vllm.model', 'Qwen/Qwen2.5-VL-7B-Instruct')
    
    @property
    def vllm_temperature(self) -> float:
        return self.get('vllm.temperature', 0.1)
    
    @property
    def vllm_max_tokens(self) -> int:
        return self.get('vllm.max_tokens', 3000)
    
    @property
    def pipeline_timeout(self) -> int:
        return self.get('pipeline.timeout', 120)
    
    @property
    def pipeline_dpi(self) -> int:
        return self.get('pipeline.dpi', 150)
    
    @property
    def pipeline_max_retries(self) -> int:
        return self.get('pipeline.max_retries', 3)
    
    @property
    def pipeline_max_pages(self) -> int:
        return self.get('pipeline.max_pages', 20)
    
    @property
    def output_format(self) -> str:
        return self.get('output.format', 'pdf')
    
    @property
    def temp_dir(self) -> Path:
        return Path(self.get('output.temp_dir', './temp'))
    
    @property
    def output_dir(self) -> Path:
        return Path(self.get('output.output_dir', './output'))
    
    @property
    def log_level(self) -> str:
        return self.get('logging.level', 'INFO')
    
    @property
    def log_format(self) -> str:
        return self.get('logging.format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    @property
    def log_file(self) -> str:
        return self.get('logging.file', './logs/audit.log')
    
    # 新增：分层审核配置
    @property
    def layered_audit_enabled(self) -> bool:
        return self.get('pipeline.layered_audit.enabled', True)
    
    @property
    def layered_audit_chunk_size(self) -> int:
        return self.get('pipeline.layered_audit.chunk_size', 3)
    
    @property
    def layered_audit_max_concurrent_chunks(self) -> int:
        return self.get('pipeline.layered_audit.max_concurrent_chunks', 3)
    
    @property
    def layered_audit_trigger_page_count(self) -> int:
        return self.get('pipeline.layered_audit.trigger_page_count', 20)


# 全局配置实例
_config_instance = None


def get_config(config_path: str = "config/config.yaml") -> Config:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance

