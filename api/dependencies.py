"""依赖注入。"""

from __future__ import annotations

from fastapi import Depends

from nacos_skill_client.cache import SkillCache
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config


def get_config() -> Config:
    return Config.load()


def get_client(config: Config = Depends(get_config)) -> NacosSkillClient:
    cache = None
    if config.cache.enabled:
        cache = SkillCache(cache_dir=config.cache.dir)
    return NacosSkillClient(config=config, cache=cache)
