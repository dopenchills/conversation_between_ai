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

    with open("output.txt", "w") as f:
        f.write(response_message.content)


if __name__ == "__main__":
    main()
