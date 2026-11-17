import json
import runpy
from pathlib import Path

import aws_cdk as cdk
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _synth_app(env, tmp_path, monkeypatch):
    """Synthesize the real app.py for `env` and return its templates by stack."""
    context = json.loads((REPO_ROOT / "cdk.json").read_text())["context"]
    app = cdk.App(context={**context, "env": env}, outdir=str(tmp_path))
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(cdk, "App", lambda: app)
    runpy.run_path(str(REPO_ROOT / "app.py"))
    return {
        path.name: json.loads(path.read_text())
        for path in tmp_path.glob("*.template.json")
    }


@pytest.mark.parametrize("env", ["dev", "stage", "prod"])
def test_every_lambda_in_the_app_has_an_errors_alarm_that_notifies(
    env, tmp_path, monkeypatch
):
    templates = _synth_app(env, tmp_path, monkeypatch)
    assert len(templates) == 7

    function_count = 0
    for name, template in templates.items():
        resources = template.get("Resources", {})
        functions = {
            logical_id
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::Lambda::Function"
        }
        alarms = [
            resource["Properties"]
            for resource in resources.values()
            if resource["Type"] == "AWS::CloudWatch::Alarm"
            and resource["Properties"].get("Namespace") == "AWS/Lambda"
        ]
        alarmed = {
            dim["Value"]["Ref"]
            for alarm in alarms
            for dim in alarm["Dimensions"]
            if dim["Name"] == "FunctionName"
        }
        assert alarmed == functions, name
        for alarm in alarms:
            assert alarm["MetricName"] == "Errors", name
            assert alarm["AlarmActions"] and alarm["OKActions"], name
        function_count += len(functions)

    assert function_count >= 2
