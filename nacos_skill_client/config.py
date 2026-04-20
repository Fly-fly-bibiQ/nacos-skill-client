"""Nacos Skill Client 配置管理。

Pydantic-settings + YAML 配置加载，环境变量优先。

环境变量命名规则：
  配置项 nacos.server_addr → 环境变量 NACOS_SKILL_NACOS_SERVER_ADDR
  配置项 llm.base_url     → 环境变量 NACOS_SKILL_LLM_BASE_URL
  即：前缀 NACOS_SKILL_ + 配置路径大写（点号 → 下划线）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 子配置模型
# --------------------------------------------------------------------------- #


class NacosConfig(BaseModel):
    """Nacos 连接配置。

    对于 Nacos 3.x（Docker 端口映射 8002:8080, 8848:8848）：
    - login_addr: 用于登录认证的地址（端口 8848，带 /nacos 前缀）
    - server_addr: 用于 API 调用的地址（端口 8002，不带 /nacos 前缀）
    """

    server_addr: str = Field(default="http://192.168.1.118:8002", description="Nacos API 地址（不带 /nacos 前缀）")
    login_addr: str | None = Field(default=None, description="Nacos 登录地址（带 /nacos 前缀），默认同 server_addr")
    api_addr: str | None = Field(default=None, description="Nacos API 专用地址，默认同 server_addr")
    username: str = Field(default="nacos", description="Nacos 用户名")
    password: str = Field(default="nacos", description="Nacos 密码")
    namespace_id: str = Field(default="public", description="默认命名空间")
    timeout: int = Field(default=30, ge=1, description="请求超时（秒）")
    verify_ssl: bool = Field(default=True, description="是否验证 SSL 证书")
    refresh_threshold_ms: int = Field(default=300000, ge=0, description="Token 刷新阈值（毫秒）")

    def get_login_addr(self) -> str:
        """获取登录地址。"""
        return self.login_addr or self.server_addr

    def get_api_addr(self) -> str:
        """获取 API 地址。"""
        return self.api_addr or self.server_addr

    def get_login_addr(self) -> str:
        """获取登录地址。"""
        return self.login_addr or self.server_addr

    def get_server_addr(self) -> str:
        """获取服务器地址。"""
        return self.server_addr


class LLMConfig(BaseModel):
    """LLM API 配置。"""

    base_url: str = Field(default="http://192.168.1.118:8000/v1", description="LLM API 基础 URL")
    model: str = Field(default="Qwen3.6-35B-A3B-FP8", description="模型名称")
    api_key: str = Field(default="dummy", description="API Key")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="生成温度")
    max_tokens: int = Field(default=4096, ge=1, description="最大 tokens")
    timeout: int = Field(default=120, ge=1, description="请求超时（秒）")


class RouterConfig(BaseModel):
    """路由配置。"""

    max_skills_for_routing: int = Field(default=100, ge=1, description="路由时最大 Skills 数量")
    routing_temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="路由温度")
    routing_max_tokens: int = Field(default=2048, ge=1, description="路由最大 tokens")
    instruction_file_priority: list[str] = Field(
        default_factory=lambda: ["SKILL.md", "AGENTS.md", "SOUL.md"],
        description="指令文件获取优先级",
    )


class SkillLoaderConfig(BaseModel):
    """Skill Loader 配置（借鉴 skills-agent-proto 的三层加载机制）。

    Level 1: scan_skills_metadata() — 启动时解析 frontmatter（name+description）
    Level 2: load_skill_metadata() — 按需加载完整 SKILL.md 指令内容
    Level 3: LLM 从指令中自己发现脚本
    """

    file_priority: list[str] = Field(
        default_factory=lambda: ["SKILL.md", "AGENTS.md", "SOUL.md"],
        description="指令文件获取优先级",
    )
    max_metadata_count: int = Field(default=200, ge=1, description="元数据发现最大数量")
    cache_metadata: bool = Field(default=True, description="是否缓存已扫描的元数据")
    metadata_cache_ttl_minutes: int = Field(default=60, ge=1, description="元数据缓存过期时间（分钟）")


class PaginationConfig(BaseModel):
    """分页配置。"""

    default_page_size: int = Field(default=50, ge=1, le=1000, description="默认每页数量")
    max_page_size: int = Field(default=200, ge=1, description="最大每页数量")


class APIConfig(BaseModel):
    """FastAPI 服务配置。"""

    host: str = Field(default="0.0.0.0", description="API 监听地址")
    port: int = Field(default=8899, ge=1, le=65535, description="API 监听端口")
    reload: bool = Field(default=False, description="开发模式自动重载")
    log_level: str = Field(default="info", description="日志级别")


class CacheConfig(BaseModel):
    """本地缓存配置。"""

    enabled: bool = Field(default=True, description="是否启用本地缓存")
    dir: str = Field(default=".skill_cache", description="缓存目录")
    ttl_days: int = Field(default=7, ge=1, description="缓存有效期（天）")


class LoggingConfig(BaseModel):
    """日志配置。"""

    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(
        default="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        description="日志格式",
    )


class AgentConfig(BaseModel):
    """Agent 配置。"""

    enabled: bool = Field(default=False, description="是否启用 Agent 模式")
    llm_provider: str = Field(default="openai", description="LLM provider (openai/anthropic/local)")
    model_name: str = Field(default="gpt-4o-mini", description="模型名称")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0, description="生成温度")
    max_iterations: int = Field(default=10, ge=1, description="最大思考轮次")
    max_time: int = Field(default=120, ge=1, description="最大执行时间(秒)")
    max_skills_to_load: int = Field(default=50, ge=1, description="最大加载 Skill 数量")
    agent_type: str = Field(default="tool-calling", description="Agent 类型 (tool-calling/react)")


# --------------------------------------------------------------------------- #
# 主配置
# --------------------------------------------------------------------------- #


class Config(BaseSettings):
    """主配置类。

    加载顺序（优先级从高到低）：
    1. 环境变量（NACOS_SKILL_*）
    2. .env 文件
    3. YAML 配置文件
    4. Pydantic 默认值
    """

    model_config = SettingsConfigDict(
        env_prefix="NACOS_SKILL_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # 子配置
    nacos: NacosConfig = Field(default_factory=NacosConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    skill_loader: SkillLoaderConfig = Field(default_factory=SkillLoaderConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "Config":
        """从 YAML 文件加载配置。"""
        path = Path(yaml_path)
        if not path.exists():
            logger.warning("YAML 配置文件不存在: %s，使用默认值", yaml_path)
            return cls()

        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.error("解析 YAML 失败: %s, %s", yaml_path, exc)
            return cls()

        # 递归合并嵌套模型
        merged: dict[str, Any] = {}
        for section, values in data.items():
            if isinstance(values, dict):
                merged[section] = values
            else:
                merged[section] = values

        return cls(**merged)

    @classmethod
    def load(cls, yaml_path: str | Path | None = None) -> "Config":
        """加载配置。

        Args:
            yaml_path: YAML 配置文件路径。如果为 None，使用项目内置默认值。

        Returns:
            配置实例（环境变量优先覆盖）。
        """
        if yaml_path:
            return cls.from_yaml(yaml_path)

        # 尝试从项目根目录加载 config/default.yaml
        candidates = [
            Path("config/default.yaml"),
            Path(__file__).parent.parent / "config" / "default.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return cls.from_yaml(candidate)

        return cls()

    def get_api_addr(self) -> str:
        """获取 API 地址，若未设置则回退到 server_addr。"""
        return self.nacos.api_addr or self.nacos.server_addr

    def setup_logging(self) -> None:
        """根据配置初始化日志。"""
        import logging as _logging

        _logging.basicConfig(
            level=getattr(_logging, self.logging.level.upper(), _logging.INFO),
            format=self.logging.format,
        )
