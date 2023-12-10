```json
{
  "name": "talk_to_ai",
  "description": "Use this function to send message to AI",
  "parameters": {
    "type": "object",
    "properties": {
      "metadata": {
        "type": "object",
        "properties": {
          "continue": {
            "type": "boolean",
            "description": "Whether we should continue this conversation. Yes: true, No: false"
          }
        },
        "required": ["continue"]
      },
      "payload": {
        "type": "object",
        "properties": {
          "to": {
            "type": "string",
            "enum": ["HUMAN", "AI"],
            "description": "To whom this message is sent to. Allowed values: HUMAN, AI"
          },
          "message": {
            "type": "string",
            "description": "message you are going to send"
          }
        },
        "required": ["to", "message"]
      }
    }
  },
  "required": ["metadata", "payload"]
}
```

```json
{
  "name": "talk_to_ai",
  "description": "Use this function to send message to AI",
  "parameters": {
    "type": "object",
    "properties": {
      "continue": {
        "type": "boolean",
        "description": "Whether we should continue this conversation. Yes: true, No: false"
      }
    }
  },
  "required": ["continue"]
}
```
