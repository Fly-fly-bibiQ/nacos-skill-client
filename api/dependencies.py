"""依赖注入。"""

from __future__ import annotations

import threading
from fastapi import Depends

from nacos_skill_client.agent.manager import AgentManager
from nacos_skill_client.cache import SkillCache
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config
from nacos_skill_client.tools.loader import NacosToolLoader

_lock = threading.Lock()
_agent_manager_instance: AgentManager | None = None


def get_config() -> Config:
    return Config.load()


def get_client(config: Config = Depends(get_config)) -> NacosSkillClient:
    cache = None
    if config.cache.enabled:
        cache = SkillCache(cache_dir=config.cache.dir)
    return NacosSkillClient(config=config, cache=cache)


def get_agent_manager(
    config: Config = Depends(get_config),
    client: NacosSkillClient = Depends(get_client),
) -> AgentManager:
    """获取 AgentManager 单例（懒初始化）。"""
    global _agent_manager_instance
    if _agent_manager_instance is None:
        with _lock:
            if _agent_manager_instance is None:
                loader = NacosToolLoader(client=client, config=config)
                _agent_manager_instance = AgentManager(config=config, loader=loader)
    return _agent_manager_instance
