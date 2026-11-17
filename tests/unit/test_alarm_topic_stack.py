import aws_cdk as cdk
import aws_cdk.assertions as assertions

from src.alarm_topic_stack import AlarmTopicStack
from src.lambda_error_alarms import LambdaErrorAlarms


def _template(slack_webhook_url=""):
    app = cdk.App()
    stack = AlarmTopicStack(
        app,
        "Alarms",
        notification_email="test@example.com",
        slack_webhook_url=slack_webhook_url,
    )
    cdk.Aspects.of(app).add(LambdaErrorAlarms(stack.alarm_topic))
    return assertions.Template.from_stack(stack)


def test_creates_topic_with_email_subscription():
    template = _template()
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {"Protocol": "email", "Endpoint": "test@example.com"},
    )


def test_exports_topic_arn():
    assert any("AlarmTopicArn" in key for key in _template().find_outputs("*"))


def test_no_slack_lambda_without_webhook():
    _template().resource_count_is("AWS::Lambda::Function", 0)


def test_slack_lambda_with_webhook_has_errors_alarm():
    template = _template("https://hooks.slack.com/services/T/B/x")
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm", {"Namespace": "AWS/Lambda", "MetricName": "Errors"}
    )
