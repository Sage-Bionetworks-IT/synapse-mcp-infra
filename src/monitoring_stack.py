from typing import Any, Dict

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

# Default alarm thresholds applied when not specified in config
_DEFAULT_ALARMS = {
    "ecs_cpu_threshold": 80,
    "ecs_memory_threshold": 80,
    "alb_5xx_threshold": 10,
    "alb_p99_latency_threshold": 5,
    "unhealthy_host_threshold": 1,
    "healthy_host_min": 1,
    "running_task_min": 1,
}


class MonitoringStack(cdk.Stack):
    """
    Optional monitoring stack that creates CloudWatch alarms, an SNS notification
    topic, and an optional CloudWatch dashboard for ECS services.

    This stack is opt-in: it is only created when MONITORING.enabled is true
    in the environment config.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        service: ecs.FargateService,
        cluster: ecs.Cluster,
        load_balancer: elbv2.ApplicationLoadBalancer,
        target_group: elbv2.ApplicationTargetGroup,
        monitoring_config: Dict[str, Any],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        alarm_config = {**_DEFAULT_ALARMS, **monitoring_config.get("alarms", {})}
        notification_email = monitoring_config["notification_email"]
        slack_webhook_url = monitoring_config.get("slack_webhook_url", "")
        enable_dashboard = monitoring_config.get("enable_dashboard", True)

        # ------------------------------------------------------------------ #
        # SNS Topic + Subscriptions
        # ------------------------------------------------------------------ #
        self.alarm_topic = sns.Topic(
            self, "AlarmTopic", display_name=f"{construct_id}-alarms"
        )

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

        alarm_action = cw_actions.SnsAction(self.alarm_topic)

        # ------------------------------------------------------------------ #
        # CloudWatch Alarms
        # ------------------------------------------------------------------ #
        cpu_alarm = cw.Alarm(
            self,
            "EcsCpuHigh",
            metric=service.metric_cpu_utilization(
                period=cdk.Duration.minutes(1),
                statistic="Average",
            ),
            threshold=alarm_config["ecs_cpu_threshold"],
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="ECS service CPU utilization is high",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        cpu_alarm.add_alarm_action(alarm_action)
        cpu_alarm.add_ok_action(alarm_action)

        memory_alarm = cw.Alarm(
            self,
            "EcsMemoryHigh",
            metric=service.metric_memory_utilization(
                period=cdk.Duration.minutes(1),
                statistic="Average",
            ),
            threshold=alarm_config["ecs_memory_threshold"],
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="ECS service memory utilization is high — risk of OOM",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        memory_alarm.add_alarm_action(alarm_action)
        memory_alarm.add_ok_action(alarm_action)

        error_5xx_alarm = cw.Alarm(
            self,
            "Alb5xxErrors",
            metric=load_balancer.metric_http_code_elb(
                code=elbv2.HttpCodeElb.ELB_5XX_COUNT,
                period=cdk.Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=alarm_config["alb_5xx_threshold"],
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="ALB is returning elevated 5xx errors",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        error_5xx_alarm.add_alarm_action(alarm_action)
        error_5xx_alarm.add_ok_action(alarm_action)

        p99_alarm = cw.Alarm(
            self,
            "AlbP99Latency",
            metric=load_balancer.metric_target_response_time(
                period=cdk.Duration.minutes(1),
                statistic="p99",
            ),
            threshold=alarm_config["alb_p99_latency_threshold"],
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="ALB P99 target response time is high",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        p99_alarm.add_alarm_action(alarm_action)
        p99_alarm.add_ok_action(alarm_action)

        unhealthy_alarm = cw.Alarm(
            self,
            "UnhealthyHosts",
            metric=target_group.metric_unhealthy_host_count(
                period=cdk.Duration.minutes(1),
                statistic="Maximum",
            ),
            threshold=alarm_config["unhealthy_host_threshold"],
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="ALB target group has unhealthy hosts",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        unhealthy_alarm.add_alarm_action(alarm_action)
        unhealthy_alarm.add_ok_action(alarm_action)

        healthy_alarm = cw.Alarm(
            self,
            "HealthyHostsLow",
            metric=target_group.metric_healthy_host_count(
                period=cdk.Duration.minutes(1),
                statistic="Minimum",
            ),
            threshold=alarm_config["healthy_host_min"],
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            alarm_description="ALB target group has fewer healthy hosts than expected",
            treat_missing_data=cw.TreatMissingData.BREACHING,
        )
        healthy_alarm.add_alarm_action(alarm_action)
        healthy_alarm.add_ok_action(alarm_action)

        running_tasks_alarm = cw.Alarm(
            self,
            "RunningTasksZero",
            metric=cw.Metric(
                namespace="ECS/ContainerInsights",
                metric_name="RunningTaskCount",
                dimensions_map={
                    "ClusterName": cluster.cluster_name,
                    "ServiceName": service.service_name,
                },
                period=cdk.Duration.minutes(1),
                statistic="Minimum",
            ),
            threshold=alarm_config["running_task_min"],
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            alarm_description="ECS service has no running tasks — service is down",
            treat_missing_data=cw.TreatMissingData.MISSING,
        )
        running_tasks_alarm.add_alarm_action(alarm_action)
        running_tasks_alarm.add_ok_action(alarm_action)

        # ------------------------------------------------------------------ #
        # CloudWatch Dashboard (optional)
        # ------------------------------------------------------------------ #
        if enable_dashboard:
            dashboard = cw.Dashboard(
                self,
                "Dashboard",
                dashboard_name=f"{construct_id}-overview",
                default_interval=cdk.Duration.hours(3),
            )

            # -- ECS Service section --
            dashboard.add_widgets(
                cw.TextWidget(markdown="# ECS Service", width=24, height=1)
            )
            dashboard.add_widgets(
                cw.GraphWidget(
                    title="CPU Utilization (%)",
                    left=[
                        service.metric_cpu_utilization(
                            statistic="Average",
                            period=cdk.Duration.minutes(1),
                        )
                    ],
                    width=12,
                ),
                cw.GraphWidget(
                    title="Memory Utilization (%)",
                    left=[
                        service.metric_memory_utilization(
                            statistic="Average",
                            period=cdk.Duration.minutes(1),
                        )
                    ],
                    width=12,
                ),
            )

            # -- Load Balancer section --
            dashboard.add_widgets(
                cw.TextWidget(markdown="# Load Balancer", width=24, height=1)
            )
            dashboard.add_widgets(
                cw.GraphWidget(
                    title="Requests & Errors",
                    left=[
                        load_balancer.metric_request_count(
                            statistic="Sum",
                            label="Requests",
                            period=cdk.Duration.minutes(1),
                        )
                    ],
                    right=[
                        load_balancer.metric_http_code_elb(
                            code=elbv2.HttpCodeElb.ELB_4XX_COUNT,
                            statistic="Sum",
                            label="4XX",
                            period=cdk.Duration.minutes(1),
                        ),
                        load_balancer.metric_http_code_elb(
                            code=elbv2.HttpCodeElb.ELB_5XX_COUNT,
                            statistic="Sum",
                            label="5XX",
                            period=cdk.Duration.minutes(1),
                        ),
                    ],
                    width=12,
                ),
                cw.GraphWidget(
                    title="Target Response Time",
                    left=[
                        load_balancer.metric_target_response_time(
                            statistic="p50",
                            label="p50",
                            period=cdk.Duration.minutes(1),
                        ),
                        load_balancer.metric_target_response_time(
                            statistic="p90",
                            label="p90",
                            period=cdk.Duration.minutes(1),
                        ),
                        load_balancer.metric_target_response_time(
                            statistic="p99",
                            label="p99",
                            period=cdk.Duration.minutes(1),
                        ),
                    ],
                    width=12,
                ),
            )

            # -- Health section --
            dashboard.add_widgets(
                cw.TextWidget(markdown="# Health", width=24, height=1)
            )
            dashboard.add_widgets(
                cw.GraphWidget(
                    title="Host Health",
                    left=[
                        target_group.metric_healthy_host_count(
                            statistic="Average",
                            label="Healthy",
                            period=cdk.Duration.minutes(1),
                        ),
                        target_group.metric_unhealthy_host_count(
                            statistic="Average",
                            label="Unhealthy",
                            period=cdk.Duration.minutes(1),
                        ),
                    ],
                    width=8,
                ),
                cw.GraphWidget(
                    title="Active Connections",
                    left=[
                        load_balancer.metric_active_connection_count(
                            statistic="Sum",
                            label="Active",
                            period=cdk.Duration.minutes(1),
                        )
                    ],
                    width=8,
                ),
                cw.GraphWidget(
                    title="Running Tasks (alarm if zero)",
                    left=[
                        cw.Metric(
                            namespace="ECS/ContainerInsights",
                            metric_name="RunningTaskCount",
                            dimensions_map={
                                "ClusterName": cluster.cluster_name,
                                "ServiceName": service.service_name,
                            },
                            period=cdk.Duration.minutes(1),
                            statistic="Minimum",
                            label="Running Tasks",
                        )
                    ],
                    left_annotations=[
                        cw.HorizontalAnnotation(
                            value=alarm_config["running_task_min"],
                            label=f"Alarm threshold ({alarm_config['running_task_min']})",
                            color=cw.Color.RED,
                        )
                    ],
                    width=8,
                ),
            )

            dashboard_url = (
                f"https://{self.region}.console.aws.amazon.com"
                f"/cloudwatch/home#dashboards:name={construct_id}-overview"
            )
            cdk.CfnOutput(
                self,
                "DashboardUrl",
                value=dashboard_url,
                description="CloudWatch dashboard URL",
            )
