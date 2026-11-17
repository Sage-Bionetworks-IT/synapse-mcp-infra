import aws_cdk as cdk
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct


class AlarmTopicStack(cdk.Stack):
    """
    SNS topic that every alarm in the app notifies. It is its own stack, deployed
    first, so the network and ECS stacks can alarm to it without a dependency cycle
    through the monitoring stack.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        notification_email: str,
        slack_webhook_url: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.alarm_topic = sns.Topic(self, "AlarmTopic", display_name=construct_id)

        self.alarm_topic.add_subscription(subs.EmailSubscription(notification_email))

        if slack_webhook_url:
            slack_handler = lambda_.Function(
                self,
                "SlackNotifier",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="index.handler",
                code=lambda_.Code.from_asset("src/lambda/slack_notifier"),
                environment={"WEBHOOK_URL": slack_webhook_url},
                timeout=cdk.Duration.seconds(10),
            )
            self.alarm_topic.add_subscription(subs.LambdaSubscription(slack_handler))

        cdk.CfnOutput(
            self,
            "AlarmTopicArn",
            value=self.alarm_topic.topic_arn,
            description="SNS topic ARN for alarm notifications",
        )
