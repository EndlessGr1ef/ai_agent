"""Stream processing utilities."""

import re
from typing import List, Tuple, Optional


class StreamProcessor:
    """Process streaming chunks and extract thinking/answer content."""

    def __init__(self):
        """Initialize the stream processor."""
        self.reasoning_buffer = ""
        self.text_buffer = ""
        self.content_accumulator = ""
        self.reasoning_found = False
        self.answer_found = False

    def reset(self):
        """Reset buffers for a new stream."""
        self.reasoning_buffer = ""
        self.text_buffer = ""
        self.content_accumulator = ""
        self.reasoning_found = False
        self.answer_found = False

    def process_chunk(self, chunk_content: str) -> Tuple[Optional[str], Optional[str]]:
        """Process a streaming chunk and extract thinking and answer content.

        Args:
            chunk_content: The content from the current chunk

        Returns:
            Tuple of (thinking_content, answer_content) or (None, None) if no new content
        """
        if not chunk_content:
            return None, None

        # Accumulate content
        self.content_accumulator += chunk_content

        # Initialize return values
        thinking_content = None
        answer_content = None

        # Look for complete thinking tags in the accumulated content
        while '<think>' in self.content_accumulator and '</think>' in self.content_accumulator:
            # Find the first complete thinking block
            start = self.content_accumulator.find('<think>')
            end = self.content_accumulator.find('</think>', start) + len('</think>')

            # Extract thinking text (between tags)
            thinking_text = self.content_accumulator[
                start + len('<think>'):self.content_accumulator.find('</think>', start)
            ]

            # Extract text before thinking
            before_thinking = self.content_accumulator[:start]

            # Check if there's new answer content before thinking
            if before_thinking:
                new_text = before_thinking[len(self.text_buffer):] if self.text_buffer else before_thinking
                if new_text:
                    answer_content = new_text
                    self.text_buffer = before_thinking
                    self.answer_found = True

            # Check if there's new thinking content
            new_thinking = thinking_text[len(self.reasoning_buffer):] if self.reasoning_buffer else thinking_text
            if new_thinking:
                thinking_content = new_thinking
                self.reasoning_buffer = thinking_text
                self.reasoning_found = True

            # Keep everything after the thinking block for next iteration
            self.content_accumulator = self.content_accumulator[end:]
            self.text_buffer = ""  # Reset text buffer to allow new content to be displayed

        # Display remaining content that doesn't contain complete thinking
        if self.content_accumulator and '<think>' not in self.content_accumulator:
            new_text = self.content_accumulator[len(self.text_buffer):] if self.text_buffer else self.content_accumulator
            if new_text:
                answer_content = new_text
                self.text_buffer = self.content_accumulator
                self.answer_found = True

        return thinking_content, answer_content

    def get_stats(self) -> dict:
        """Get processing statistics."""
        return {
            'reasoning_found': self.reasoning_found,
            'answer_found': self.answer_found,
        }
