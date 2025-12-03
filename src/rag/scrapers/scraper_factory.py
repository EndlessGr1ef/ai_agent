"""
爬虫工厂类
"""

from typing import Dict, Any, Optional
import logging

from .prts_wiki_scraper import PRTSWikiScraper
from .character_scraper import CharacterScraper
from .story_scraper import StoryScraper
from .base_scraper import BaseScraper


class ScraperFactory:
    """爬虫工厂类 - 负责创建不同类型的爬虫实例"""

    # 支持的爬虫类型
    SCRAPER_TYPES = {
        'character': CharacterScraper,
        'characters': CharacterScraper,
        '干员': CharacterScraper,
        'story': StoryScraper,
        'stories': StoryScraper,
        '剧情': StoryScraper,
        'plot': StoryScraper,
        'general': PRTSWikiScraper,
        'auto': None  # 自动检测
    }

    @classmethod
    def create_scraper(
        cls,
        scraper_type: str,
        output_dir: Optional[str] = None,
        **kwargs
    ) -> BaseScraper:
        """
        创建指定类型的爬虫实例

        Args:
            scraper_type: 爬虫类型 ('character', 'story', 'auto')
            output_dir: 输出目录
            **kwargs: 传递给爬虫的其他参数

        Returns:
            BaseScraper: 爬虫实例

        Raises:
            ValueError: 如果不支持的爬虫类型
        """
        # 标准化类型名称
        scraper_type = scraper_type.lower().strip()

        # 检查是否支持
        if scraper_type not in cls.SCRAPER_TYPES:
            raise ValueError(
                f"Unsupported scraper type: {scraper_type}. "
                f"Supported types: {list(cls.SCRAPER_TYPES.keys())}"
            )

        # 自动检测类型
        if scraper_type == 'auto':
            # auto类型需要通过其他方式确定，暂时使用默认类型
            scraper_class = PRTSWikiScraper
        else:
            scraper_class = cls.SCRAPER_TYPES[scraper_type]

        # 创建实例
        try:
            if scraper_class == CharacterScraper:
                # 干员爬虫参数
                instance = CharacterScraper(
                    output_dir=output_dir or "docs/prts/干员",
                    **kwargs
                )
            elif scraper_class == PRTSWikiScraper:
                # 通用爬虫参数
                instance = PRTSWikiScraper(
                    output_dir=output_dir or "docs/prts",
                    **kwargs
                )
            elif scraper_class == StoryScraper:
                # 剧情爬虫参数
                instance = StoryScraper(
                    output_dir=output_dir or "docs/prts/剧情",
                    **kwargs
                )
            else:
                # 默认情况
                instance = scraper_class(**kwargs)

            return instance

        except Exception as e:
            logging.error(f"Failed to create scraper of type {scraper_type}: {e}")
            raise

    @classmethod
    def get_available_types(cls) -> list:
        """
        获取所有可用的爬虫类型

        Returns:
            list: 可用的爬虫类型列表
        """
        return list(cls.SCRAPER_TYPES.keys())

    @classmethod
    def is_valid_type(cls, scraper_type: str) -> bool:
        """
        检查是否为有效的爬虫类型

        Args:
            scraper_type: 爬虫类型

        Returns:
            bool: 是否有效
        """
        return scraper_type.lower().strip() in cls.SCRAPER_TYPES

    @classmethod
    def get_scraper_info(cls, scraper_type: str) -> Dict[str, str]:
        """
        获取爬虫类型信息

        Args:
            scraper_type: 爬虫类型

        Returns:
            Dict[str, str]: 爬虫信息
        """
        scraper_type = scraper_type.lower().strip()

        info_map = {
            'character': {
                'name': '干员爬虫',
                'description': '专门用于爬取干员信息页面',
                'target': '干员页面',
                'features': '技能、天赋、属性、精英化信息'
            },
            'story': {
                'name': '剧情爬虫',
                'description': '专门用于爬取剧情内容',
                'target': '剧情页面',
                'features': '对话、旁白、章节、角色'
            },
            'general': {
                'name': '通用爬虫',
                'description': '通用网页爬虫',
                'target': '通用页面',
                'features': '基础内容提取'
            }
        }

        return info_map.get(scraper_type, {
            'name': '未知',
            'description': '未知类型',
            'target': '未知',
            'features': '未知'
        })

    @classmethod
    def suggest_type_by_url(cls, url: str) -> str:
        """
        根据URL建议合适的爬虫类型

        Args:
            url: 页面URL

        Returns:
            str: 建议的爬虫类型
        """
        url_lower = url.lower()

        # 剧情相关关键词
        if any(keyword in url_lower for keyword in [
            '剧情', '故事', '活动', '剧情回顾',
            'side story', 'event', '世界观', '设定'
        ]):
            return 'story'

        # 干员相关关键词
        if any(keyword in url_lower for keyword in [
            '干员', '角色', '技能', '天赋',
            'character', 'operator'
        ]):
            return 'character'

        # 默认类型
        return 'character'


def create_scraper(
    scraper_type: str,
    output_dir: Optional[str] = None,
    **kwargs
) -> BaseScraper:
    """
    便利函数 - 创建爬虫实例

    Args:
        scraper_type: 爬虫类型
        output_dir: 输出目录
        **kwargs: 其他参数

    Returns:
        BaseScraper: 爬虫实例
    """
    return ScraperFactory.create_scraper(scraper_type, output_dir, **kwargs)


def get_scraper_info(scraper_type: str) -> Dict[str, str]:
    """
    便利函数 - 获取爬虫信息

    Args:
        scraper_type: 爬虫类型

    Returns:
        Dict[str, str]: 爬虫信息
    """
    return ScraperFactory.get_scraper_info(scraper_type)


def suggest_scraper_type(url: str) -> str:
    """
    便利函数 - 根据URL建议爬虫类型

    Args:
        url: 页面URL

    Returns:
        str: 建议的爬虫类型
    """
    return ScraperFactory.suggest_type_by_url(url)
