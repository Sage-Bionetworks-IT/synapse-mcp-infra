import importlib
import json
import sys
from pathlib import Path


def _load_handler(monkeypatch, webhook_url="https://hooks.slack.com/services/T/B/x"):
    monkeypatch.setenv("WEBHOOK_URL", webhook_url)
    lambda_dir = Path(__file__).resolve().parents[2] / "src" / "lambda" / "slack_notifier"
    monkeypatch.syspath_prepend(str(lambda_dir))
    sys.modules.pop("index", None)
    return importlib.import_module("index")


def test_handler_posts_slack_payload(monkeypatch):
    captured = {}

    def fake_urlopen(req, *args, **kwargs):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data

        class _Resp:
            def read(self):
                return b""

        return _Resp()

    handler_module = _load_handler(monkeypatch)
    monkeypatch.setattr(handler_module.urllib.request, "urlopen", fake_urlopen)

    event = {
        "Records": [
            {"Sns": {"Subject": "ALARM: ecs-cpu", "Message": "CPU > 80%"}}
        ]
    }
    result = handler_module.handler(event, None)

    assert result == {"statusCode": 200}
    assert captured["url"] == "https://hooks.slack.com/services/T/B/x"
    assert captured["headers"]["Content-type"] == "application/json"
    body = json.loads(captured["body"])
    assert body == {"text": "*ALARM: ecs-cpu*\nCPU > 80%"}
