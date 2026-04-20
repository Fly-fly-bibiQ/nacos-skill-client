"""本地 Skill 缓存模块。

缓存结构::

    .skill_cache/
    ├── <skill_name>/
    │   ├── AGENTS.md
    │   ├── SOUL.md
    │   └── manifest.json   (记录 version, download_time, name, description)
    └── ...

典型用法::

    from nacos_skill_client.cache import SkillCache

    cache = SkillCache()
    if cache.has_skill("翻译助手"):
        content = cache.get_skill_file("翻译助手", "AGENTS.md")
    else:
        # 从 Nacos 下载并缓存
        content = client.get_skill_md("翻译助手")
        cache.save_skill("翻译助手", content, "AGENTS.md")
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillCache:
    """本地 Skill 缓存。

    将 Skill 的指令文件缓存在本地磁盘，避免重复从 Nacos 下载。

    Attributes:
        cache_dir: 缓存根目录路径。
    """

    MANIFEST_FILENAME = "manifest.json"

    def __init__(self, cache_dir: str = ".skill_cache") -> None:
        """初始化缓存。

        Args:
            cache_dir: 缓存目录路径，默认为项目根目录下的 `.skill_cache/`。
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("SkillCache initialized at %s", self.cache_dir)

    def _skill_dir(self, name: str) -> Path:
        """获取某个 Skill 的缓存目录。

        Args:
            name: Skill 名称。

        Returns:
            Skill 缓存目录 Path。
        """
        # 用安全的文件名
        safe_name = self._safe_filename(name)
        return self.cache_dir / safe_name

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将 Skill 名称转为安全的文件名。

        对 ASCII 保留字母数字和 -/_, 中文字符转为 unicode hex 编码。
        """
        safe = ""
        for ch in name:
            if ch.isascii() and (ch.isalnum() or ch in ('-', '_')):
                safe += ch
            elif not ch.isascii():
                # 中文等非 ASCII 字符用 hex 编码，保证唯一性
                safe += '_' + format(ord(ch), 'x')
            else:
                safe += '_'
        return safe or "unknown_skill"

    def has_skill(self, name: str) -> bool:
        """检查某个 Skill 是否已缓存。

        检查条件：
        1. Skill 目录存在
        2. manifest.json 存在

        Args:
            name: Skill 名称。

        Returns:
            已缓存返回 True，否则 False。
        """
        skill_dir = self._skill_dir(name)
        manifest_path = skill_dir / self.MANIFEST_FILENAME
        return skill_dir.is_dir() and manifest_path.is_file()

    def get_skill_manifest(self, name: str) -> dict[str, Any] | None:
        """获取 Skill 的 manifest 信息。

        Args:
            name: Skill 名称。

        Returns:
            manifest 字典，不存在返回 None。
        """
        manifest_path = self._skill_dir(name) / self.MANIFEST_FILENAME
        if not manifest_path.is_file():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read manifest for %s: %s", name, exc)
            return None

    def get_skill_file(self, name: str, filename: str) -> tuple[str | None, str | None]:
        """获取 Skill 的指定文件内容。

        Args:
            name: Skill 名称。
            filename: 文件名（如 AGENTS.md, SOUL.md）。

        Returns:
            (file_label, content) 元组。文件不存在时返回 (None, None)。
        """
        skill_dir = self._skill_dir(name)
        file_path = skill_dir / filename
        if not file_path.is_file():
            return (None, None)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.debug("Cache hit: %s/%s (%d chars)", name, filename, len(content))
            return (filename, content)
        except OSError as exc:
            logger.warning("Failed to read cached file %s/%s: %s", name, filename, exc)
            return (None, None)

    def save_skill(self, name: str, content: str, filename: str,
                   version: str = "", description: str = "") -> None:
        """保存 Skill 的指定文件到缓存。

        Args:
            name: Skill 名称。
            content: 文件内容。
            filename: 文件名（如 AGENTS.md）。
            version: 版本号（可选）。
            description: 描述（可选，写入 manifest）。
        """
        skill_dir = self._skill_dir(name)
        skill_dir.mkdir(parents=True, exist_ok=True)

        file_path = skill_dir / filename
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.debug("Cached skill %s/%s (%d chars)", name, filename, len(content))
        except OSError as exc:
            logger.error("Failed to save cached file %s/%s: %s", name, filename, exc)
            return

        # 更新 manifest
        self._update_manifest(name, version=version, description=description)

    def _update_manifest(self, name: str, version: str = "", description: str = "") -> None:
        """更新 Skill 的 manifest 文件。"""
        manifest_path = self._skill_dir(name) / self.MANIFEST_FILENAME
        manifest = {
            "name": name,
            "version": version,
            "description": description,
            "download_time": int(time.time() * 1000),  # 毫秒时间戳
        }
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Failed to save manifest for %s: %s", name, exc)

    def get_all_cached_skills(self) -> list[str]:
        """获取所有已缓存的 Skill 名称（安全文件名）。

        Returns:
            已缓存的 Skill 名称列表。
        """
        if not self.cache_dir.is_dir():
            return []
        skills = []
        for item in self.cache_dir.iterdir():
            if item.is_dir():
                manifest = item / self.MANIFEST_FILENAME
                if manifest.is_file():
                    try:
                        with open(manifest, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        skills.append(data.get("name", item.name))
                    except (json.JSONDecodeError, OSError):
                        skills.append(item.name)
        return skills
