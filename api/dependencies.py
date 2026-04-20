"""依赖注入。"""

from __future__ import annotations

from fastapi import Depends

from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config


def get_config() -> Config:
    return Config.load()


def get_client(config: Config = Depends(get_config)) -> NacosSkillClient:
    return NacosSkillClient(config=config)
