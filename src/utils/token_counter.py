"""Token counting utilities."""

import re
from typing import List


def count_tokens_in_messages(messages: List) -> int:
    """Calculate the total number of tokens in the message list.

    Args:
        messages: List of messages (SystemMessage, HumanMessage, AIMessage)

    Returns:
        Total token count
    """
    try:
        # Try to import tokenizer from context_compressor
        from context_compressor import tokenizer as hf_tokenizer, HAS_TOKENIZER as COMPRESSOR_HAS_TOKENIZER

        if COMPRESSOR_HAS_TOKENIZER and hf_tokenizer:
            total = 0
            for msg in messages:
                total += len(hf_tokenizer.encode(msg.content))
            return total
    except Exception:
        pass

    # Fallback: approximate token count
    total = 0
    for msg in messages:
        # Rough approximation: 1 token ≈ 4 characters for English, 1.5 for Chinese
        text = msg.content
        english_chars = len(re.findall(r'[a-zA-Z0-9\s]', text))
        chinese_chars = len(text) - english_chars
        total += int(english_chars / 4 + chinese_chars / 1.5)
    return total
