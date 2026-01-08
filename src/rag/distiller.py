import os
import re
import json
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from src.config.llm_config import build_anthropic_llm, require_api_key

class KnowledgeDistiller:
    """
    PRTS Knowledge Distillation Engine.
    Refines raw Wiki content into high-density, structured information.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or require_api_key()
        # Default to MiniMax-M2.1 which is confirmed to work with Coding Plan
        self.model = os.getenv("OPENAI_MODEL", "MiniMax-M2.1")
        self.client = build_anthropic_llm(
            api_key=self.api_key,
            model=self.model
        )

    def clean_noise(self, content: str) -> str:
        """Remove Wiki templates, tables, and other noise."""
        # 1. Remove YAML headers
        content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
        
        # 2. Remove {{...}} templates (often nested)
        # A simple non-nested regex first
        content = re.sub(r'\{\{[^{}]*\}\}', '', content)
        # Second pass for one level of nesting
        content = re.sub(r'\{\{[^{}]*\}\}', '', content)
        
        # 3. Remove [[File:...]] or [[Category:...]]
        content = re.sub(r'\[\[(?:File|Category|category|文件|Category|分类):[^\]]*\]\]', '', content)
        
        # 4. Remove HTML tags and comments
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', '', content)
        
        # 5. Remove excessive whitespace and redundant lines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 6. Specific Arknights Wiki noise
        content = re.sub(r'\[查看属性\]', '', content)
        content = re.sub(r'\[查看基建\]', '', content)
        
        return content.strip()

    def classify(self, content: str, file_path: str) -> str:
        """Classify content type for specialized distillation."""
        content_lower = content.lower()
        path_lower = file_path.lower()
        
        if 'content_type: story' in content_lower or '/story' in path_lower or '剧情' in path_lower:
            return 'story'
        if 'content_type: character' in content_lower or '/operator' in path_lower or '干员' in path_lower:
            return 'operator'
        
        # Check for dialogue indicators
        if '**' in content and ':' in content:
            return 'story'
            
        return 'general'

    async def distill(self, content: str, metadata: Dict[str, Any]) -> str:
        """Main entry point for distillation."""
        doc_type = metadata.get('doc_type') or self.classify(content, metadata.get('source', ''))
        
        cleaned = self.clean_noise(content)
        
        # If content is too short after cleaning, just return it
        if len(cleaned) < 100:
            return cleaned
            
        if doc_type == 'operator':
            distilled = await self._distill_operator(cleaned, metadata)
        elif doc_type == 'story':
            distilled = await self._distill_story(cleaned, metadata)
        else:
            distilled = await self._distill_general(cleaned, metadata)
            
        if not distilled:
            return ""
            
        # Add a simplified YAML header for ingest_md.py to detect
        header = f"---\ntitle: {metadata.get('title', 'Unknown')}\ncontent_type: {doc_type}\nis_distilled: true\nsource: {metadata.get('source', 'Unknown')}\n---\n\n"
        return header + distilled

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM with retries and handle different block types."""
        max_retries = 3
        base_delay = 2.0  # seconds
        
        for attempt in range(max_retries):
            try:
                # Add a small delay between requests to avoid rate limits
                # Exponential backoff for retries
                delay = base_delay * (2 ** attempt) if attempt > 0 else 1.0
                await asyncio.sleep(delay)
                
                # Use run_in_executor for the blocking Anthropic call
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model=self.model,
                        max_tokens=2500,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                        temperature=0.1
                    )
                )
                
                # Find the first TextBlock or content that has 'text'
                text_content = ""
                for block in response.content:
                    if hasattr(block, 'text'):
                        text_content += block.text
                    elif isinstance(block, dict) and 'text' in block:
                        text_content += block['text']
                    
                return text_content.strip()
            except Exception as e:
                # If rate limited, wait longer
                if "429" in str(e) or "limit exceeded" in str(e).lower():
                    if attempt < max_retries - 1:
                        print(f"[RETRY] Rate limited on attempt {attempt + 1}. Waiting {delay * 2}s...")
                        continue
                print(f"[ERROR] Distillation call failed: {e}")
                return ""
        return ""

    async def _distill_operator(self, content: str, metadata: Dict[str, Any]) -> str:
        system_prompt = """你是一位专业的罗德岛档案管理员。你的任务是从原始的Wiki数据中提炼干员的高密度、结构化核心档案。
请忽略所有的游戏数值（如攻击力、生命值）、技能等级倍率、Wiki模板代码等非核心信息。

输出应包含以下核心板块：
1. **干员概况**：代号、出身、职业、星级。
2. **战斗侧写**：核心战斗机制、战术定位、能力特点（如“法术伤害爆发”、“强力生存控制”）。
3. **性格与履历**：性格特点、加入罗德岛的原因、在罗德岛的表现或特殊地位。
4. **关键秘密/背景**：档案中提及的特殊背景、机密信息或伏笔（如有）。

要求：
- 使用高度精炼的专业语言，体现罗德岛数据库的风格。
- 采用Markdown格式，使用清晰的标题。
- 剔除所有冗余描述，只保留核心信息。"""
        
        user_prompt = f"请提炼以下干员原始数据（来源：{metadata.get('source', '未知')}）：\n\n{content}"
        return await self._call_llm(system_prompt, user_prompt)

    async def _distill_story(self, content: str, metadata: Dict[str, Any]) -> str:
        system_prompt = """你是一位明日方舟剧情分析专家。你的任务是从原始的剧情记录中提炼高密度、叙事化的剧情梗概。
请忽略所有的游戏对话标记（如 [Amiya]、**Amiya**:）、多余的旁白描述、Wiki代码。

输出应包含以下核心板块：
1. **剧情背景**：发生的时间、地点、所属章节/活动。
2. **关键人物**：本次剧情涉及的核心角色及其关键行动。
3. **核心冲突**：剧情中的主要矛盾点、战斗原因或转折。
4. **结局与影响**：剧情的最终走向，以及对整体世界观或后续剧情的意义。

要求：
- 使用高度精炼的叙事化语言，逻辑严密。
- 采用Markdown格式，结构清晰。
- 确保剧情连贯，保留关键的伏笔或真相揭示。"""
        
        user_prompt = f"请提炼以下剧情原始数据（标题：{metadata.get('title', '未知')}）：\n\n{content}"
        return await self._call_llm(system_prompt, user_prompt)

    async def _distill_general(self, content: str, metadata: Dict[str, Any]) -> str:
        system_prompt = """你是一位明日方舟世界观研究专家。你的任务是将以下关于明日方舟的原始信息提炼为高密度、易于检索的结构化知识库条目。
剔除所有的Wiki噪音、格式代码和冗余描述。

要求：
- 采用Markdown格式，使用清晰的层级标题。
- 保留所有核心事实、专有名词、时间节点和关键关系。
- 语言简练，确保每一句话都包含有效信息。"""
        
        user_prompt = f"请提炼以下原始数据（来源：{metadata.get('source', '未知')}）：\n\n{content}"
        return await self._call_llm(system_prompt, user_prompt)

