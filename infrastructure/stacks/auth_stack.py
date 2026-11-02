"""
AWS CDK Stack: Authentication & User Management (Cognito User Pool & Trigger).
Author: Nguyễn Đức Huy (Nhóm 10 - SatiBot)
"""

import os
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
)
from constructs import Construct


class AuthStack(Stack):
    """
    Stack hạ tầng quản lý danh tính người dùng và xác thực qua Amazon Cognito.
    Cung cấp:
      - Cognito User Pool (đăng nhập bằng email, password policy chuẩn an toàn, tự động xác thực email)
      - Cognito User Pool Client (dành cho Web Frontend SPA, không client secret)
      - Lambda Post Confirmation Trigger (tự động ghi User Profile vào DynamoDB)
      - Phân quyền nhóm người dùng (User Groups: 'admin' và 'user')
      - CloudFormation Outputs phục vụ liên kết hạ tầng (Export UserPoolId, ClientId)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        users_table_name: str = "SatiBot-Users",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.users_table_name = users_table_name

        # 1. Lambda Function: Post-Confirmation Trigger
        backend_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )

        self.post_confirmation_fn = _lambda.Function(
            self,
            "CognitoPostConfirmationHandler",
            function_name="SatiBot-CognitoPostConfirmation",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="functions.auth_handler.index.lambda_handler",
            code=_lambda.Code.from_asset(backend_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "USERS_TABLE_NAME": self.users_table_name,
                "ADMIN_EMAILS": os.environ.get("ADMIN_EMAILS", "admin@satibot.com"),
                "DEFAULT_REGION": self.region,
            },
            description="Trigger Cognito tự động tạo User Profile trong DynamoDB sau khi xác nhận đăng ký.",
        )

        # Cấp quyền IAM cho Lambda thao tác trên bảng DynamoDB Users
        self.post_confirmation_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.users_table_name}"
                ],
            )
        )

        # 2. Amazon Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "SatiBotUserPool",
            user_pool_name="SatiBot-UserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(
                email=True,
                username=False,
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                fullname=cognito.StandardAttribute(required=False, mutable=True),
            ),
            custom_attributes={
                "role": cognito.StringAttribute(mutable=True),
            },
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(7),
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
            lambda_triggers=cognito.UserPoolTriggers(
                post_confirmation=self.post_confirmation_fn,
            ),
        )

        # 3. Amazon Cognito User Pool Client (Dành cho Web Frontend SPA)
        self.user_pool_client = self.user_pool.add_client(
            "SatiBotWebClient",
            user_pool_client_name="SatiBot-WebClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
            prevent_user_existence_errors=True,
        )

        # 4. Phân nhóm người dùng Cognito User Groups (Admin / User)
        self.admin_group = cognito.CfnUserPoolGroup(
            self,
            "AdminUserGroup",
            group_name="admin",
            user_pool_id=self.user_pool.user_pool_id,
            description="Nhóm quản trị viên hệ thống có toàn quyền quản trị tài nguyên",
            precedence=1,
        )

        self.user_group = cognito.CfnUserPoolGroup(
            self,
            "StandardUserGroup",
            group_name="user",
            user_pool_id=self.user_pool.user_pool_id,
            description="Nhóm người dùng tiêu chuẩn",
            precedence=10,
        )

        # 5. CloudFormation Outputs
        CfnOutput(
            self,
            "UserPoolIdOutput",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
            export_name="SatiBot-UserPoolId",
        )

        CfnOutput(
            self,
            "UserPoolArnOutput",
            value=self.user_pool.user_pool_arn,
            description="Cognito User Pool ARN",
            export_name="SatiBot-UserPoolArn",
        )

        CfnOutput(
            self,
            "UserPoolClientIdOutput",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito Web Client ID",
            export_name="SatiBot-UserPoolClientId",
        )
