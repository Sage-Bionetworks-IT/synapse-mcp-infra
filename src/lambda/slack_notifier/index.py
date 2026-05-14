import json
import os
import urllib.request

WEBHOOK_URL = os.environ["WEBHOOK_URL"]


def handler(event, context):
    for record in event["Records"]:
        sns_message = record["Sns"]
        payload = json.dumps(
            {"text": f"*{sns_message['Subject']}*\n{sns_message['Message']}"}
        ).encode("utf-8")
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
    return {"statusCode": 200}
