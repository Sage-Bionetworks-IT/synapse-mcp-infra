import aws_cdk as cdk

from src.ecs_stack import EcsStack
from src.load_balancer_stack import LoadBalancerStack
from src.network_stack import NetworkStack
from src.redis_stack import RedisStack
from src.service_props import ServiceProps, ServiceSecret
from src.service_stack import LoadBalancedServiceStack
from src.utils import load_context_config

cdk_app = cdk.App()
env_name = cdk_app.node.try_get_context("env") or "dev"
config = load_context_config(env_name=env_name)
STACK_NAME_PREFIX = f"synapse-mcp-{env_name}"
FQDN = config["FQDN"]
TAGS = config["TAGS"]
APP_VERSION = "latest"

# recursively apply tags to all stack resources
if TAGS:
    for key, value in TAGS.items():
        cdk.Tags.of(cdk_app).add(key, value)

network_stack = NetworkStack(
    scope=cdk_app,
    construct_id=f"{STACK_NAME_PREFIX}-network",
    vpc_cidr=config["VPC_CIDR"],
)

ecs_stack = EcsStack(
    scope=cdk_app,
    construct_id=f"{STACK_NAME_PREFIX}-ecs",
    vpc=network_stack.vpc,
    namespace=FQDN,
)

# From AWS docs https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect-concepts-deploy.html
# The public discovery and reachability should be created last by AWS CloudFormation, including the frontend
# client service. The services need to be created in this order to prevent an time period when the frontend
# client service is running and available the public, but a backend isn't.
load_balancer_stack = LoadBalancerStack(
    scope=cdk_app,
    construct_id=f"{STACK_NAME_PREFIX}-load-balancer",
    vpc=network_stack.vpc,
)
load_balancer_stack.add_dependency(ecs_stack)

app_props = ServiceProps(
    ecs_task_cpu=512,
    ecs_task_memory=1024,
    container_name="synapse-mcp",
    container_location="ghcr.io/sage-bionetworks/synapse-mcp:v0.2.1",
    container_port=9000,
    container_env_vars={
        "MCP_SERVER_URL": f"https://{FQDN}/mcp",
        "MCP_TRANSPORT": "streamable-http",
        "SYNAPSE_OAUTH_REDIRECT_URI": f"https://{FQDN}/oauth/callback",
        "SYNAPSE_MCP_CLIENT_REGISTRY_BACKEND": "redis",
        "SYNAPSE_ENV": config.get("MCP_SERVER_ENV"),
        "SYNAPSE_OAUTH_CLIENT_ID": config.get("SYNAPSE_OAUTH_CLIENT_ID"),
    },
    container_secrets=[
        ServiceSecret(
            secret_name=f"{STACK_NAME_PREFIX}/oauth-client-secretval",
            environment_key="SYNAPSE_OAUTH_CLIENT_SECRET",
        ),
    ],
)
app_stack = LoadBalancedServiceStack(
    scope=cdk_app,
    construct_id=f"{STACK_NAME_PREFIX}-app",
    vpc=network_stack.vpc,
    cluster=ecs_stack.cluster,
    props=app_props,
    load_balancer=load_balancer_stack.alb,
    health_check_path="/health",
    enable_https=True,
    certificate_arn=config.get("CERTIFICATE_ARN"),
)

# Create Valkey stack (Serverless - Redis-compatible)
redis_stack = RedisStack(
    scope=cdk_app,
    construct_id=f"{STACK_NAME_PREFIX}-redis",
    vpc=network_stack.vpc,
    engine_version=config.get("VALKEY_ENGINE_VERSION", "8.2"),
    max_ecpu_per_second=config.get("VALKEY_MAX_ECPU_PER_SECOND", 1000),
    max_storage_gb=config.get("VALKEY_MAX_STORAGE_GB", 1),
)

# Add Valkey URL to app service environment variables (using REDIS_URL for compatibility)
app_stack.container.add_environment("REDIS_URL", redis_stack.redis_url)

# Ensure Redis stack is created before app stack
app_stack.add_dependency(redis_stack)

cdk_app.synth()
