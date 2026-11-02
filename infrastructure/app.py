import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.core_api_stack import CoreApiStack
from stacks.ai_stack import AiStack
from stacks.data_stack import DataStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

auth_stack = AuthStack(app, "AuthStack")
CoreApiStack(app, "CoreApiStack", user_pool=auth_stack.user_pool)
AiStack(app, "AiStack")
DataStack(app, "DataStack")
MonitoringStack(app, "MonitoringStack")

app.synth()
