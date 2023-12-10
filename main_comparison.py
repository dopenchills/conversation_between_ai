import os
from datetime import datetime
from typing import List

import openai


def main():
    purpose = input("目的を入力してください: ")

    chat_messages: List[openai.types.chat.ChatCompletionMessageParam] = [
        {"role": "user", "content": purpose},
    ]

    response = openai.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=chat_messages,
    )

    response_message = response.choices[0].message

    output_dir = "output_comparison/summary"

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    payload_head = response_message.content[:20].replace("\n", " ")
    file_name = f"{timestamp}_{payload_head}.md"

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(os.path.join(output_dir, file_name), "w") as f:
        f.write(response_message.content)


if __name__ == "__main__":
    main()
