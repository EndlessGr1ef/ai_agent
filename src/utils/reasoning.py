"""Reasoning details extraction utilities."""

from langchain_core.messages import AIMessage


def extract_reasoning_details(ai_msg: AIMessage):
    """Try to extract provider-specific reasoning details from AIMessage."""
    try:
        # Try additional_kwargs first (common for reasoning)
        if hasattr(ai_msg, "additional_kwargs") and ai_msg.additional_kwargs:
            rd = ai_msg.additional_kwargs.get("reasoning_details")
            if rd:
                return rd

        # Try response_metadata
        if hasattr(ai_msg, "response_metadata") and ai_msg.response_metadata:
            meta = ai_msg.response_metadata
            # Check common reasoning keys
            for key in ("reasoning_details", "reasoning", "thoughts", "analysis"):
                val = meta.get(key)
                if val:
                    return val

        # Try other attributes
        for attr in ("reasoning", "analysis", "thoughts"):
            if hasattr(ai_msg, attr):
                val = getattr(ai_msg, attr)
                if val:
                    return val

        # Check if chunk has special attributes
        if hasattr(ai_msg, "id") and "reasoning" in str(ai_msg.id):
            return "Processing reasoning..."

    except Exception:
        pass
    return None
