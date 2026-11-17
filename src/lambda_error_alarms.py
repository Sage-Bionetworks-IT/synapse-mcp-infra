import re
from typing import Optional

import aws_cdk as cdk
import jsii
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from constructs import IConstruct


@jsii.implements(cdk.IAspect)
class LambdaErrorAlarms:
    """
    Aspect that adds an `AWS/Lambda` `Errors` alarm, keyed on `FunctionName`,
    for every `AWS::Lambda::Function` it visits, including the ones CDK
    generates for custom resources. Each alarm lives in its function's stack.
    Alarm and OK transitions notify `alarm_topic` when given.

    Apply it to the app so it runs at synth, after every stack is built.

    Vanta's "Serverless function error rate monitored (AWS)" test only counts
    alarms with a plain `MetricName` and a `FunctionName` dimension, so the
    metric has no label (a label makes CDK emit metric math instead).
    """

    def __init__(self, alarm_topic: Optional[sns.ITopic] = None) -> None:
        self.alarm_topic = alarm_topic

    def visit(self, node: IConstruct) -> None:
        if not (
            cdk.CfnResource.is_cfn_resource(node)
            and node.cfn_resource_type == "AWS::Lambda::Function"
        ):
            return
        stack = cdk.Stack.of(node)
        path = node.node.path.removeprefix(f"{stack.node.path}/")
        alarm = cw.Alarm(
            stack,
            "LambdaErrors-" + re.sub(r"[^A-Za-z0-9]+", "-", path),
            metric=cw.Metric(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions_map={"FunctionName": node.ref},
                statistic="Sum",
                period=cdk.Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description=f"Lambda {stack.stack_name}/{path} reported errors",
        )
        if self.alarm_topic:
            alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
            alarm.add_ok_action(cw_actions.SnsAction(self.alarm_topic))
