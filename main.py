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
import os
from datetime import datetime
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
    tasks: List[str]
    next_task: str


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


class GeneralFileWriteIO(IO):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def read(self):
        pass

    def write(self, payload: str):
        with open(self.file_path, "w") as f:
            f.write(payload)


class SummaryFileWriteIO(IO):
    def __init__(self, directory="output/summary"):
        self.directory = directory

        if not os.path.exists(directory):
            os.makedirs(directory)

    def read(self):
        pass

    def write(self, payload: str):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        payload_first_10_chars = payload[:20].replace("\n", " ")
        file_name = f"{timestamp}_{payload_first_10_chars}.md"
        path = os.path.join(os.getcwd(), self.directory, file_name)

        with open(path, "w") as f:
            f.write(payload)


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
        self.purpose: Optional[str] = None

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
        self.purpose = purpose_payload["content"]

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

簡単な小タスクに分解したのち、その最初のタスクだけを振ってみてください。そしてその後の対話で他のタスクを振ってください。あなたはChatGPTの評価者でありマネージャーとして振る舞うということです。
ChatGPTが現在のタスクを完了したら、次のタスクを振ってください。
全てのタスクが完了するまで、ChatGPTと対話し続けてください。

ChatGPTから抽象的な答えが返ってきたり、あなたが期待する答えが返ってこない場合は、ChatGPTに対してより具体的な指示を出してください。

ChatGPTから得る返答には、必ず大学生でも理由が理解できるような根拠を求めてください。それがない場合は、ChatGPTに対してより具体的な根拠を求めてください。

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
        "tasks": strings[] // 目的を達成するために分割した小タスクのリスト
        "next_task": string // 次に実行するタスク
    }
}
```

""",
            },
            {"role": "user", "content": f"私> {purpose}"},
        ]

        self.chat_messages.extend(chat_messages)

        response = openai.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=chat_messages,
            response_format={"type": "json_object"},
        )

        response_message = response.choices[0].message

        if response_message.content is None:
            raise Exception(
                "Sending purpose to human failed because ManagerAI did not return any result"
            )

        talk_to_ai_response: TalkToAIArguments = json.loads(response_message.content)

        logger.info(
            f"""
==========管理者AIの考えたタスク==========
タスク:
{talk_to_ai_response["payload"]["tasks"]}

次のタスク:
{talk_to_ai_response["payload"]["next_task"]}
=======================================
"""
        )

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
                "content": f"""私> 今までの会話から私に向けてレポートを作成し、返してください。

今回の会話の目的は以下の通りです。あなたのレポートは私がこの目的を達成するために書いてください:
{self.purpose}

フォーマットはtalk_to_aiを使わないで、Markdown形式でお願いします。

## 会話のまとめ
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

            chat_history = "\n"
            for chat_message in self.chat_messages:
                chat_history += "```txt\n"
                chat_history += (
                    "[" + chat_message["role"] + "]"
                    if "role" in chat_message
                    else "[" + chat_message.role + "]"  # type: ignore
                )

                chat_history += "\n\n"

                if "content" in chat_message:
                    chat_history += (  # type: ignore
                        chat_message["content"] if "content" in chat_message else ""
                    )
                else:
                    chat_history += chat_message.content
                chat_history += "\n```\n\n"

            summary = f"""# 目的
{self.purpose}
            
# ChatGPTとの会話のまとめ
{response_message.content}

# ChatGPTとの会話の履歴
{chat_history}
"""

            self.send_message(
                {
                    "type_": MessageType.SEND_SUMMARY,
                    "payload": {"content": summary},
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
    human = Human(SummaryFileWriteIO())
    manager_ai = ManagerAI([WorkerAI()])
    message_handler = MessageHandler()

    purpose = purpose_io.read()
    human.send_purpose(purpose, manager_ai, message_handler)


if __name__ == "__main__":
    main()
