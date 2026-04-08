"""模型 provider 边界模块集合，统一暴露外部模型调用、prompt 与解析入口。"""

from .parsers import (
    extract_json_object,
    normalize_ending_analysis,
    normalize_story_node_choices,
    normalize_story_node_content,
    normalize_story_package,
    split_scene_into_paragraphs,
)
from .prompts import (
    compose_ending_analysis_prompt,
    compose_story_choice_prompt,
    compose_story_node_prompt,
    compose_story_package_prompt,
    compose_story_prompt,
)
from .secondme import call_secondme_act, call_secondme_chat
from .volcengine import (
    call_volcengine_prose,
    has_volcengine_prose_provider,
    stream_volcengine_prose_chunks,
    volcengine_chat_url,
)

__all__ = [
    "call_secondme_act",
    "call_secondme_chat",
    "call_volcengine_prose",
    "compose_ending_analysis_prompt",
    "compose_story_choice_prompt",
    "compose_story_node_prompt",
    "compose_story_package_prompt",
    "compose_story_prompt",
    "extract_json_object",
    "has_volcengine_prose_provider",
    "normalize_ending_analysis",
    "normalize_story_node_choices",
    "normalize_story_node_content",
    "normalize_story_package",
    "split_scene_into_paragraphs",
    "stream_volcengine_prose_chunks",
    "volcengine_chat_url",
]
