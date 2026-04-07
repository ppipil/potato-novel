#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def chat_url() -> str:
    base_url = os.getenv("VOLCENGINE_BASE_URL", "").strip().rstrip("/")
    chat_path = os.getenv("VOLCENGINE_CHAT_PATH", "/chat/completions").strip() or "/chat/completions"
    if not base_url:
        return ""
    if base_url.endswith("/chat/completions"):
        return base_url
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    return f"{base_url}{chat_path}"


def prompt_text() -> str:
    return """你正在补全互动小说某一个节点的正文内容。
必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。
JSON 结构必须为：{"stageLabel":"阶段标题","directorNote":"一句局势提示","scene":"2到3段正文","summary":"一句本节点摘要"}
scene 必须是中文互动小说文本，优先使用对白、动作、误会和情绪落点。

故事标题：攻略值刷满后，系统说这其实是烦躁值
玩家身份：主人公
故事开头：我一直以为校霸对我的攻略值刷满了，直到系统提示那其实是他的烦躁值。
当前节点：N2-tease (turn)
当前节点阶段：第二幕·火上浇油
当前节点戏剧功能：局势升级
当前节点路径摘要：你在第一步选择嘴硬试探，让场面更像一场带火花的拉扯。
当前节点摘要：嘴硬和撩拨把张力拉高，对方开始在认真与试探之间摇摆。
当前节点选项：
- N2-tease-C1：我抬手替他理了一下衣领：「你都快把心事写脸上了，还要我继续猜吗？」 -> N3-confession
- N2-tease-C2：我忽然认真起来：「如果你愿意说实话，这次我不会再笑着糊弄过去。」 -> N3-confession
- N2-tease-C3：我顺势把话题拐开，想先套出他背后还有没有别人参与。 -> N3-secret

请只补全当前节点的正文，使它和骨架走向一致，不要引入新的主线。"""


def main() -> int:
    load_env()
    api_key = os.getenv("VOLCENGINE_API_KEY", "").strip()
    model = os.getenv("VOLCENGINE_MODEL", "").strip()
    url = chat_url()

    if not api_key or not model or not url:
        print("Missing VOLCENGINE_API_KEY, VOLCENGINE_MODEL, or VOLCENGINE_BASE_URL/VOLCENGINE_CHAT_PATH", file=sys.stderr)
        return 1

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个擅长中文互动小说场景写作的助手。"},
            {"role": "user", "content": prompt_text()},
        ],
        "temperature": 0.9,
        "max_tokens": 1400,
    }

    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
