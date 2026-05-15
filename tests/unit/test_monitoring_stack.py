import aws_cdk as cdk
import aws_cdk.assertions as assertions

from src.ecs_stack import EcsStack
from src.load_balancer_stack import LoadBalancerStack
from src.monitoring_stack import MonitoringStack
from src.network_stack import NetworkStack
from src.service_props import ServiceProps
from src.service_stack import LoadBalancedServiceStack


def _create_monitoring_template(monitoring_config=None):
    """Helper to create a MonitoringStack and return its synthesized template."""
    if monitoring_config is None:
        monitoring_config = {
            "enabled": True,
            "notification_email": "test@example.com",
        }

    app = cdk.App()
    network = NetworkStack(app, "Net", vpc_cidr="10.0.0.0/24")
    ecs = EcsStack(
        app, "Ecs", vpc=network.vpc, namespace="test.io", container_insights=True
    )
    lb = LoadBalancerStack(app, "Lb", vpc=network.vpc)

    props = ServiceProps(
        container_name="test-app",
        container_location="nginx:latest",
        container_port=80,
        ecs_task_cpu=256,
        ecs_task_memory=512,
    )
    svc = LoadBalancedServiceStack(
        app,
        "Svc",
        vpc=network.vpc,
        cluster=ecs.cluster,
        props=props,
        load_balancer=lb.alb,
    )

    monitoring = MonitoringStack(
        app,
        "Mon",
        service=svc.service,
        cluster=ecs.cluster,
        load_balancer=lb.alb,
        target_group=svc.target_group,
        monitoring_config=monitoring_config,
    )
    return assertions.Template.from_stack(monitoring)


def test_monitoring_stack_creates_sns_topic():
    template = _create_monitoring_template()
    template.resource_count_is("AWS::SNS::Topic", 1)


def test_monitoring_stack_creates_email_subscription():
    template = _create_monitoring_template()
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {"Protocol": "email", "Endpoint": "test@example.com"},
    )


def test_monitoring_stack_creates_all_alarms():
    template = _create_monitoring_template()
    template.resource_count_is("AWS::CloudWatch::Alarm", 7)


def test_monitoring_stack_creates_dashboard_by_default():
    template = _create_monitoring_template()
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)


def test_monitoring_stack_no_dashboard_when_disabled():
    template = _create_monitoring_template(
        monitoring_config={
            "enabled": True,
            "notification_email": "test@example.com",
            "enable_dashboard": False,
        }
    )
    template.resource_count_is("AWS::CloudWatch::Dashboard", 0)


def test_monitoring_stack_custom_cpu_threshold():
    template = _create_monitoring_template(
        monitoring_config={
            "enabled": True,
            "notification_email": "test@example.com",
            "alarms": {"ecs_cpu_threshold": 70},
        }
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "Threshold": 70,
            "MetricName": "CPUUtilization",
        },
    )


def test_monitoring_stack_no_slack_lambda_without_webhook():
    template = _create_monitoring_template()
    template.resource_count_is("AWS::Lambda::Function", 0)


def test_monitoring_stack_creates_slack_lambda_with_webhook():
    template = _create_monitoring_template(
        monitoring_config={
            "enabled": True,
            "notification_email": "test@example.com",
            "slack_webhook_url": "https://hooks.slack.com/services/T/B/x",
        }
    )
    template.resource_count_is("AWS::Lambda::Function", 1)


def test_monitoring_stack_exports_topic_arn():
    template = _create_monitoring_template()
    outputs = template.find_outputs("*")
    assert any("AlarmTopicArn" in key for key in outputs)
