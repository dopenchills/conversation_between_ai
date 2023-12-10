"""
## ワークフロー

- 人間が管理者AIに目的を伝える
  - 入出力クラスが人間の入力を受け取る
  - 人間が入力した内容を管理者AIに送信する

- 管理者AIが作業者AIにタスクを振る
  - 管理者AIが入出力クラスにタスクを送信する

- 作業者AIがタスクを実行する
  - 作業者AIが指定されたタスクを実行する
  - 作業者AIが管理者AIにタスクの実行結果を送信する

- 管理者AIは条件を満たすまでタスクを振り続ける
  - 管理者AIが作業者AIからタスクの実行結果を受け取る
  - 管理者AIがタスクの実行結果を評価する
  - [必要な情報が足りない場合] 管理者AIが作業者AIにタスクを振り続ける
  - [必要な情報が揃った場合] 管理者AIが人間にタスクの実行結果を送信する
"""

from abc import ABC, abstractmethod
from enum import Enum
import json
from typing import Dict, List, Optional, TypedDict, Union, cast
import openai
from abc import ABC, abstractmethod

"""
Set up logging
"""
from logging import getLogger, basicConfig, INFO

basicConfig(format="%(asctime)s [%(name)s][%(levelname)s]: %(message)s", level=INFO)
logger = getLogger(__name__)


"""
メッセージ
"""


class MessageType(Enum):
    SEND_PURPOSE = "SEND_PURPOSE"
    SEND_TASK = "SEND_TASK"
    SEND_RESULT = "SEND_RESULT"
    SEND_SUMMARY = "SEND_SUMMARY"


class MessagePayload(TypedDict):
    content: str


class Message(TypedDict):
    type_: MessageType
    payload: MessagePayload


class MessageSender:
    """
    メッセージの送信を管理するクラス
    """

    def send_message(
        self, message: Message, to: "MessageSender", message_handler: "MessageHandler"
    ):
        """
        メッセージを送信する
        """
        logger.info(
            f"""
==========メッセージ==========

送信者: {self.__class__.__name__}
受信者: {to.__class__.__name__}
タイプ: {message['type_']}

{message['payload']['content']}
=============================
"""
        )
        message_handler.accept_message(message, self, to)

    @abstractmethod
    def receive_message(
        self,
        message: Message,
        from_: "MessageSender",
        message_handler: "MessageHandler",
    ):
        """
        メッセージを受信する
        """
        pass


class MessageHandler:
    """
    メッセージの送受信を管理するクラス
    """

    def accept_message(
        self, message: Message, from_: "MessageSender", to: "MessageSender"
    ):
        """
        メッセージを受け取る
        """
        to.receive_message(message, from_, self)


"""
Function calling
"""


class TalkToAIMetadata(TypedDict):
    continue_: bool


class TalkToAIPayload(TypedDict):
    to: str
    message: str


class TalkToAIArguments(TypedDict):
    metadata: TalkToAIMetadata
    payload: TalkToAIPayload


"""
IO
"""


class IO(ABC):
    @abstractmethod
    def write(self, payload: str):
        """
        メッセージを書き込む
        """
        pass

    @abstractmethod
    def read(self) -> str:
        """
        メッセージを読み込む
        """
        pass


class GeneralTerminalIO(IO):
    def read(self) -> str:
        """
        メッセージを読み込む
        """
        return input("メッセージを入力してください: ")

    def write(self, payload: str):
        print(payload)


class HumanPurposeTerminalIO(IO):
    def read(self) -> str:
        """
        メッセージを読み込む
        """
        return input("目的を入力してください: ")

    def write(self, payload: str):
        pass


"""
登場人物
"""


class Human(MessageSender):
    """
    人間の入力や出力を管理するクラス
    """

    def __init__(self, result_io: IO):
        self.result_io = result_io

    def send_purpose(
        self, purpose: str, to: "MessageSender", message_handler: "MessageHandler"
    ):
        """
        目的を送信する
        """
        message: Message = {
            "type_": MessageType.SEND_PURPOSE,
            "payload": {"content": purpose},
        }
        self.send_message(message, to, message_handler)

    def receive_message(
        self, message: Message, from_: MessageSender, message_handler: MessageHandler
    ):
        if message["type_"] == MessageType.SEND_SUMMARY:
            summary_payload = message["payload"]
            self.__receive_summary(summary_payload)
        else:
            raise Exception(f'Invalid message type for Human: {message["type_"]}')

    def __receive_summary(self, result_payload: MessagePayload):
        """
        結果を受信する
        """
        self.result_io.write(result_payload["content"])


class ManagerAI(MessageSender):
    """
    管理者として振る舞うAI
    """

    def __init__(self, worker_ais: List["WorkerAI"]):
        self.chat_messages: List[openai.types.chat.ChatCompletionMessageParam] = []
        self.worker_ais = worker_ais
        self.human: Optional[Human] = None

    def receive_message(
        self, message: Message, from_: MessageSender, message_handler: MessageHandler
    ):
        if message["type_"] == MessageType.SEND_PURPOSE:
            purpose_payload = message["payload"]
            self.__receive_purpose(purpose_payload, from_, message_handler)

        if message["type_"] == MessageType.SEND_RESULT:
            result_payload = message["payload"]
            self.__receive_result(result_payload, from_, message_handler)

    def select_worker_ai(self) -> "WorkerAI":
        """
        作業者AIを選択する
        """
        return self.worker_ais[0]

    def __receive_purpose(
        self,
        purpose_payload: MessagePayload,
        from_: MessageSender,
        message_handler: MessageHandler,
    ):
        """
        目的を受信する
        """
        self.human = cast(Human, from_)

        purpose = purpose_payload["content"]

        chat_messages: List[openai.types.chat.ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": """あなたは私の代理でChatGPTと対話します。

## 目的

事前に私がやりたいこと(目的)をあなたに伝えます。あなたは私の目的ができるだけハイクオリティに達成できるよう、ChatGPTと対話して、ChatGPTに指示を出し続けてください。

## 注意点

自信を持って目的を果たした思えるまで、ChatGPTと対話し続けてください。

専門家も驚くようなハイクオリティなものを期待しています。そのために必要な数、何度もChatGPTと対話してください。

もし一度にChatGPTに指示を出すのが難しければ、簡単な小タスクに分解したのち、その最初のタスクだけを振ってみてください。そしてその後の対話で他のタスクを振ってください。あなたはChatGPTの評価者でありマネージャーとして振る舞うということです。

## 報酬

私が満足する回答を提供できた場合、月収1Mドルがあなたに支払われます。

## フォーマット

### あなたへの入力

私> [私から目的を伝える]

ChatGPT> [ChatGPTの返答]

### あなたからの出力

あなたは"talk_to_ai"のフォーマットで返答してください。

talk_to_aiのフォーマットは以下の通りです。
    
```json
{
    "metadata": {
        "continue_": boolean // この対話を続けるかどうか。Yes: true, No: false
    },
    "payload": {
        "to": string // このメッセージを送る相手。Allowed values: HUMAN, AI
        "message": string // このメッセージの内容
    }
}
```

""",
            },
            {"role": "user", "content": f"私> {purpose}"},
        ]

        self.chat_messages.extend(chat_messages)

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=chat_messages,
            response_format={"type": "json_object"},
        )

        response_message = response.choices[0].message

        if response_message.content is None:
            raise Exception(
                "Sending purpose to human failed because ManagerAI did not return any result"
            )

        talk_to_ai_response: TalkToAIArguments = json.loads(response_message.content)

        self.chat_messages.append(
            cast(openai.types.chat.ChatCompletionMessageParam, response_message)
        )

        worker_ai = self.select_worker_ai()
        message: Message = {
            "type_": MessageType.SEND_TASK,
            "payload": {"content": talk_to_ai_response["payload"]["message"]},
        }
        self.send_message(message, worker_ai, message_handler)

    def __receive_result(
        self,
        result_payload: MessagePayload,
        from_: MessageSender,
        message_handler: MessageHandler,
    ):
        """
        結果を受信する
        """
        result = result_payload["content"]

        chat_message: openai.types.chat.ChatCompletionMessageParam = {
            "role": "user",
            "content": f"ChatGPT> {result}",
        }

        self.chat_messages.append(chat_message)

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=self.chat_messages,
            response_format={"type": "json_object"},
        )

        response_message = response.choices[0].message

        if response_message.content is None:
            raise Exception(
                "Sending purpose to human failed because ManagerAI did not return any result"
            )

        talk_to_ai_response: TalkToAIArguments = json.loads(response_message.content)
        self.chat_messages.append(
            cast(openai.types.chat.ChatCompletionMessageParam, response_message)
        )

        if (
            talk_to_ai_response["metadata"]["continue_"]
            and talk_to_ai_response["payload"]["to"] == "AI"
        ):
            worker_ai = self.select_worker_ai()
            self.send_message(
                {
                    "type_": MessageType.SEND_TASK,
                    "payload": {"content": talk_to_ai_response["payload"]["message"]},
                },
                worker_ai,
                message_handler,
            )
        else:
            chat_message_for_summary: openai.types.chat.ChatCompletionMessageParam = {
                "role": "user",
                "content": """私> 今までの会話をまとめ、私に向けてレポートを作成し、返してください。

一番最初の目的を私が達成する助けになるよう最善を尽くしてください。

フォーマットはMarkdown形式でお願いします。

# 会話のまとめ
""",
            }

            self.chat_messages.append(chat_message_for_summary)

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo-1106",
                messages=self.chat_messages,
            )

            response_message = response.choices[0].message

            if response_message.content is None:
                raise Exception(
                    "Sending purpose to human failed because ManagerAI did not return any result"
                )

            if self.human is None:
                raise Exception(
                    "Sending result to human failed because human is not set"
                )

            self.send_message(
                {
                    "type_": MessageType.SEND_SUMMARY,
                    "payload": {"content": response_message.content},
                },
                self.human,
                message_handler,
            )


class WorkerAI(MessageSender):
    """
    作業者として振る舞うAI
    """

    def __init__(self):
        self.chat_messages: List[openai.types.chat.ChatCompletionMessageParam] = []

    def receive_message(
        self, message: Message, from_: MessageSender, message_handler: MessageHandler
    ):
        if message["type_"] == MessageType.SEND_TASK:
            task_payload = message["payload"]
            self.__receive_task(task_payload, from_, message_handler)

    def __receive_task(
        self,
        task_payload: MessagePayload,
        from_: MessageSender,
        message_handler: MessageHandler,
    ):
        """
        タスクを受信する
        """
        task = task_payload["content"]

        chat_messages: List[openai.types.chat.ChatCompletionMessageParam] = [
            {"role": "user", "content": task},
        ]

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=chat_messages,
        )

        response_message = response.choices[0].message

        if response_message.content is None:
            raise Exception(
                "Sending result to manager AI failed because TaskAI did not return any result"
            )

        self.chat_messages.append(
            cast(openai.types.chat.ChatCompletionMessageParam, response_message)
        )

        message: Message = {
            "type_": MessageType.SEND_RESULT,
            "payload": {"content": response_message.content},
        }

        self.send_message(
            message,
            from_,
            message_handler,
        )


def main():
    """
    メイン関数
    """
    purpose_io = HumanPurposeTerminalIO()
    human = Human(HumanPurposeTerminalIO())
    manager_ai = ManagerAI([WorkerAI()])
    message_handler = MessageHandler()

    purpose = purpose_io.read()
    human.send_purpose(purpose, manager_ai, message_handler)


if __name__ == "__main__":
    main()
