#!/usr/bin/env python3
"""
Context Compressor - 智能上下文压缩工具

基于消息重要性的动态压缩算法，支持：
- 消息重要性评分
- 多级压缩策略
- Token 预算管理
- 动态调整
"""

import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

# 尝试导入 tokenizer
try:
    from transformers import GPT2Tokenizer
    tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
    HAS_TOKENIZER = True
except ImportError:
    HAS_TOKENIZER = False
    print("⚠️  未安装 transformers，将使用近似计数")


class MessageType(Enum):
    """消息类型"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class ScoredMessage:
    """带评分的消息"""
    message: any  # SystemMessage, HumanMessage, AIMessage
    score: float
    token_count: int
    type: MessageType
    content: str


class ContextCompressor:
    """上下文压缩器"""

    def __init__(self,
                 max_tokens: int = 100000,
                 min_important_score: float = 40.0,
                 compression_threshold: float = 0.8):
        """
        Args:
            max_tokens: 最大 token 数
            min_important_score: 最低重要分数（低于此分数的消息会被优先删除）
            compression_threshold: 压缩阈值（达到此比例时开始压缩）
        """
        self.max_tokens = max_tokens
        self.min_important_score = min_important_score
        self.compression_threshold = compression_threshold

        # 评分权重
        self.type_weights = {
            MessageType.SYSTEM: 100.0,
            MessageType.TOOL_RESULT: 80.0,
            MessageType.TOOL_CALL: 75.0,
            MessageType.USER: 60.0,
            MessageType.ASSISTANT: 50.0,
        }

        # 压缩统计
        self.stats = {
            "original_count": 0,
            "compressed_count": 0,
            "tokens_saved": 0,
            "compression_ratio": 0.0
        }

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数"""
        if HAS_TOKENIZER:
            return len(tokenizer.encode(text))
        else:
            # 近似计算：英文按 4 字符/token，中文按 1.5 字符/token
            english_chars = len(re.findall(r'[a-zA-Z0-9\s]', text))
            chinese_chars = len(text) - english_chars
            return int(english_chars / 4 + chinese_chars / 1.5)

    def get_message_type(self, message) -> MessageType:
        """识别消息类型"""
        message_str = str(message.__class__.__name__)

        if "System" in message_str:
            return MessageType.SYSTEM
        elif "Human" in message_str or "User" in message_str:
            return MessageType.USER
        elif "AIMessage" in message_str or "Assistant" in message_str:
            return MessageType.ASSISTANT
        else:
            return MessageType.ASSISTANT

    def score_message(self, message: any, position: int, total: int) -> float:
        """
        消息重要性评分

        评分因素：
        1. 消息类型权重
        2. 位置权重（新消息更重要）
        3. 内容特征（代码、列表、决策等）
        4. 长度权重（过短或过长都减分）
        """
        msg_type = self.get_message_type(message)
        content = getattr(message, 'content', str(message))

        # 1. 基础类型分数
        base_score = self.type_weights[msg_type]

        # 2. 位置权重（越新越高）
        recency_score = (position / total) * 20  # 0-20 分

        # 3. 内容特征加分
        content_bonus = 0

        # 代码块加分
        if "```" in content or "<code>" in content:
            content_bonus += 15

        # 列表/要点加分
        if re.search(r'^\s*[-*•]\s+', content, re.MULTILINE):
            content_bonus += 10

        # 数字/日期加分（可能是重要数据）
        if re.search(r'\d+', content):
            content_bonus += 5

        # 决策性语言加分
        if re.search(r'(决定|选择|确定|应该|需要|要求)', content):
            content_bonus += 10

        # 4. 长度权重（太短或太长都减分）
        token_count = self.count_tokens(content)
        if token_count < 10:
            length_penalty = (10 - token_count) * 0.5
        elif token_count > 1000:
            length_penalty = (token_count - 1000) * 0.01
        else:
            length_penalty = 0

        # 5. 系统消息特殊处理
        if msg_type == MessageType.SYSTEM:
            # 系统消息始终保持高分
            return 100.0

        final_score = base_score + recency_score + content_bonus - length_penalty

        return max(0, min(100, final_score))

    def should_compress(self, messages: List[ScoredMessage]) -> bool:
        """判断是否需要压缩"""
        total_tokens = sum(m.token_count for m in messages)
        return total_tokens > (self.max_tokens * self.compression_threshold)

    def merge_consecutive_messages(self, messages: List[ScoredMessage]) -> List[ScoredMessage]:
        """合并连续的用户/助手对话"""
        if len(messages) < 2:
            return messages

        merged = []
        i = 0

        while i < len(messages):
            current = messages[i]

            # 尝试合并连续的用户和助手消息
            if (i + 1 < len(messages) and
                current.type in [MessageType.USER, MessageType.ASSISTANT] and
                messages[i + 1].type in [MessageType.ASSISTANT, MessageType.USER]):

                # 合并为对话块
                combined_content = f"{current.content}\n\n{messages[i + 1].content}"
                combined_score = (current.score + messages[i + 1].score) / 2

                merged_message = ScoredMessage(
                    message=None,  # 合并后的消息没有原始对象
                    score=combined_score,
                    token_count=current.token_count + messages[i + 1].token_count,
                    type=MessageType.ASSISTANT,
                    content=combined_content
                )

                merged.append(merged_message)
                i += 2  # 跳过已合并的两个消息
            else:
                merged.append(current)
                i += 1

        return merged

    def summarize_long_messages(self, messages: List[ScoredMessage]) -> List[ScoredMessage]:
        """对过长的消息进行摘要"""
        summarized = []

        for msg in messages:
            if msg.token_count > 500:  # 超过 500 tokens 的消息需要摘要
                # 简单摘要策略：保留开头、关键中间部分、结尾
                content = msg.content
                lines = content.split('\n')

                if len(lines) > 10:
                    # 保留前 3 行、中间关键行、后 3 行
                    summary = '\n'.join(lines[:3] + ['...(内容已压缩)...'] + lines[-3:])

                    summarized_msg = ScoredMessage(
                        message=msg.message,
                        score=msg.score * 0.8,  # 摘要降低重要性
                        token_count=int(msg.token_count * 0.4),  # 压缩到 40%
                        type=msg.type,
                        content=summary
                    )
                    summarized.append(summarized_msg)
                else:
                    summarized.append(msg)
            else:
                summarized.append(msg)

        return summarized

    def prune_low_score_messages(self, messages: List[ScoredMessage],
                                 target_token_count: int) -> List[ScoredMessage]:
        """删除低分消息以达到目标 token 数"""
        if not messages:
            return messages

        # 按分数排序（高分优先）
        sorted_messages = sorted(messages, key=lambda m: m.score, reverse=True)

        # 保留系统消息
        system_messages = [m for m in sorted_messages if m.type == MessageType.SYSTEM]
        other_messages = [m for m in sorted_messages if m.type != MessageType.SYSTEM]

        # 计算系统消息的 token 数
        system_token_count = sum(m.token_count for m in system_messages)
        available_tokens = target_token_count - system_token_count

        # 逐个添加其他消息，直到达到 token 限制
        selected = system_messages.copy()
        current_token_count = system_token_count

        for msg in other_messages:
            if current_token_count + msg.token_count <= available_tokens:
                selected.append(msg)
                current_token_count += msg.token_count
            else:
                break

        # 按原始顺序排序
        selected.sort(key=lambda m: messages.index(m) if m in messages else 0)

        return selected

    def compress(self, messages: List[any]) -> List[any]:
        """
        压缩消息列表

        步骤：
        1. 计算当前 token 数
        2. 为每条消息评分
        3. 如果需要压缩，依次应用：
           - 合并连续消息
           - 摘要长消息
           - 删除低分消息
        4. 返回压缩后的消息
        """
        if not messages:
            return messages

        # 记录原始状态
        original_count = len(messages)
        original_tokens = sum(self.count_tokens(getattr(m, 'content', str(m))) for m in messages)

        # 创建带评分的信息
        scored_messages = []
        for i, msg in enumerate(messages):
            content = getattr(msg, 'content', str(msg))
            token_count = self.count_tokens(content)

            scored_msg = ScoredMessage(
                message=msg,
                score=self.score_message(msg, i, len(messages)),
                token_count=token_count,
                type=self.get_message_type(msg),
                content=content
            )
            scored_messages.append(scored_msg)

        # 检查是否需要压缩
        if not self.should_compress(scored_messages):
            self.stats = {
                "original_count": original_count,
                "compressed_count": original_count,
                "tokens_saved": 0,
                "compression_ratio": 0.0
            }
            return messages

        # 应用压缩策略
        compressed = scored_messages.copy()

        # 策略 1: 合并连续消息
        compressed = self.merge_consecutive_messages(compressed)

        # 策略 2: 摘要长消息
        compressed = self.summarize_long_messages(compressed)

        # 策略 3: 删除低分消息
        if self.should_compress(compressed):
            # 计算目标 token 数（保留 80%）
            target_tokens = int(self.max_tokens * 0.8)
            compressed = self.prune_low_score_messages(compressed, target_tokens)

        # 转换回原始消息格式
        result = []
        for msg in compressed:
            if msg.message is not None:
                result.append(msg.message)
            else:
                # 合并的消息需要创建新对象
                # 这里简化处理，实际应该根据类型创建
                from langchain_core.messages import AIMessage
                result.append(AIMessage(content=msg.content))

        # 更新统计
        compressed_tokens = sum(m.token_count for m in compressed)
        self.stats = {
            "original_count": original_count,
            "compressed_count": len(result),
            "tokens_saved": original_tokens - compressed_tokens,
            "compression_ratio": (original_tokens - compressed_tokens) / original_tokens
        }

        return result

    def get_stats(self) -> Dict:
        """获取压缩统计信息"""
        return self.stats

    def print_stats(self):
        """打印压缩统计信息"""
        stats = self.get_stats()
        print(f"\n📊 上下文压缩统计:")
        print(f"  原始消息数: {stats['original_count']}")
        print(f"  压缩后消息数: {stats['compressed_count']}")
        print(f"  节省 tokens: {stats['tokens_saved']}")
        print(f"  压缩率: {stats['compression_ratio']:.1%}")


def create_compressor(max_tokens: int = 100000) -> ContextCompressor:
    """创建压缩器实例"""
    return ContextCompressor(max_tokens=max_tokens)


# 示例用法
if __name__ == "__main__":
    # 创建测试消息
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    messages = [
        SystemMessage(content="你是一个有用的助手。"),
        HumanMessage(content="你好"),
        AIMessage(content="你好！有什么可以帮助你的吗？"),
        HumanMessage(content="请告诉我什么是机器学习"),
        AIMessage(content="""机器学习是人工智能的一个分支，它使计算机能够在没有明确编程的情况下学习。机器学习算法使用统计技术来从数据中"学习"，并做出预测或决策。机器学习有三种主要类型：

1. 监督学习：使用标记数据训练模型
2. 无监督学习：从未标记数据中发现模式
3. 强化学习：通过试错学习最佳行动

机器学习应用广泛，包括图像识别、自然语言处理、推荐系统等。"""),
        HumanMessage(content="谢谢，这很有用"),
        AIMessage(content="很高兴能帮到你！还有其他问题吗？"),
    ]

    # 创建压缩器
    compressor = create_compressor(max_tokens=500)  # 设置较低限制用于测试

    # 压缩消息
    print("压缩前消息数:", len(messages))
    compressed_messages = compressor.compress(messages)
    print("压缩后消息数:", len(compressed_messages))

    # 打印统计
    compressor.print_stats()
