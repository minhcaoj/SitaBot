"""
AWS CDK Stack: Core API Gateway với Cognito JWT Authorizer.
Định tuyến và bảo mật các endpoints ChatOps (/chat, /confirm, /history, /connect).
Author: Nguyễn Đức Huy (Nhóm 10 - SatiBot)
"""

import os
from typing import Optional
from aws_cdk import (
    CfnOutput,
    Duration,
    Fn,
    Stack,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
)
from constructs import Construct


class CoreApiStack(Stack):
    """
    Stack trung tâm điều phối API Gateway:
      - Quản lý API Gateway REST API phục vụ Web Frontend (React)
      - Tích hợp Amazon Cognito User Pools Authorizer bảo vệ 100% các route nhạy cảm
      - Điều hướng traffic tới các Lambda functions (Chatbot, History, Connector)
      - Bật cấu hình CORS chuẩn cho các nguồn truy cập web
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool: Optional[cognito.IUserPool] = None,
        user_pool_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Liên kết User Pool phục vụ Authorizer
        if user_pool is not None:
            self.user_pool = user_pool
        elif user_pool_id:
            self.user_pool = cognito.UserPool.from_user_pool_id(
                self, "ImportedUserPoolById", user_pool_id=user_pool_id
            )
        else:
            # Fallback import từ CloudFormation Export do AuthStack xuất ra
            imported_pool_id = Fn.import_value("SatiBot-UserPoolId")
            self.user_pool = cognito.UserPool.from_user_pool_id(
                self, "ImportedUserPoolFromExport", user_pool_id=imported_pool_id
            )

        # 2. Khởi tạo Cognito User Pools Authorizer trên API Gateway
        self.authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "SatiBotCognitoAuthorizer",
            cognito_user_pools=[self.user_pool],
            authorizer_name="SatiBot-CognitoAuthorizer",
            identity_source="method.request.header.Authorization",
            results_cache_ttl=Duration.minutes(5),
        )

        # 3. Khởi tạo API Gateway REST API
        self.api = apigateway.RestApi(
            self,
            "SatiBotCoreApi",
            rest_api_name="SatiBot-CoreApi",
            description="API Gateway trung tâm điều phối ChatOps và bảo vệ bởi Cognito JWT Authorizer.",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=[
                    "Authorization",
                    "Content-Type",
                    "X-Amz-Date",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
            ),
        )

        # 4. Định nghĩa Lambda Functions điều phối
        backend_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )

        # 4.1. Chatbot Lambda (Xử lý Chat & Confirm)
        self.chatbot_fn = _lambda.Function(
            self,
            "ChatbotLambdaFunction",
            function_name="SatiBot-ChatbotService",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="functions.chatbot.index.lambda_handler",
            code=_lambda.Code.from_asset(backend_dir),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "DEFAULT_REGION": self.region,
                "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
            },
            description="Tiếp nhận chat tiếng Việt, gọi LLM Tool Calling và xử lý phê duyệt hành động.",
        )

        # 4.2. History Lambda (Tra cứu lịch sử Chat & Action)
        self.history_fn = _lambda.Function(
            self,
            "HistoryLambdaFunction",
            function_name="SatiBot-HistoryService",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="functions.history.index.lambda_handler",
            code=_lambda.Code.from_asset(backend_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "ACTION_HISTORY_TABLE": os.environ.get("ACTION_HISTORY_TABLE", "SatiBot-ActionHistory"),
            },
            description="Truy xuất lịch sử thao tác người dùng.",
        )

        # 4.3. Connector Lambda (Quản lý AWS Credentials người dùng)
        self.connector_fn = _lambda.Function(
            self,
            "ConnectorLambdaFunction",
            function_name="SatiBot-ConnectorService",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="functions.connector.index.lambda_handler",
            code=_lambda.Code.from_asset(backend_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "AWS_CONNECTIONS_TABLE": os.environ.get("AWS_CONNECTIONS_TABLE", "SatiBot-AwsConnections"),
            },
            description="Quản lý và mã hóa kết nối IAM Credentials của khách hàng.",
        )

        # 5. Cấu hình các Route / Endpoint và gắn Cognito Authorizer
        auth_options = {
            "authorizer": self.authorizer,
            "authorization_type": apigateway.AuthorizationType.COGNITO,
        }

        # 5.1. Route: POST /chat (Gửi câu hỏi / yêu cầu thao tác)
        chat_resource = self.api.root.add_resource("chat")
        chat_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.chatbot_fn),
            **auth_options,
        )

        # 5.2. Route: POST /confirm (Xác nhận phê duyệt hành động)
        confirm_resource = self.api.root.add_resource("confirm")
        confirm_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.chatbot_fn),
            **auth_options,
        )

        # 5.3. Route: GET /history (Lấy lịch sử hội thoại)
        history_resource = self.api.root.add_resource("history")
        history_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.history_fn),
            **auth_options,
        )

        # 5.4. Route: POST & GET /connect (Quản lý AWS Credentials kết nối)
        connect_resource = self.api.root.add_resource("connect")
        connect_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.connector_fn),
            **auth_options,
        )
        connect_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.connector_fn),
            **auth_options,
        )

        # 6. CloudFormation Outputs
        CfnOutput(
            self,
            "ApiGatewayUrlOutput",
            value=self.api.url,
            description="Đường dẫn gốc API Gateway",
            export_name="SatiBot-ApiGatewayUrl",
        )

        CfnOutput(
            self,
            "ApiGatewayIdOutput",
            value=self.api.rest_api_id,
            description="API Gateway ID",
            export_name="SatiBot-ApiGatewayId",
        )

        CfnOutput(
            self,
            "AuthorizerIdOutput",
            value=self.authorizer.authorizer_id,
            description="Cognito Authorizer ID",
            export_name="SatiBot-AuthorizerId",
        )
