"""
Unit tests cho AWS CDK CoreApiStack (API Gateway REST API, Cognito JWT Authorizer, Endpoints).
Author: Nguyễn Đức Huy (Nhóm 10 - SatiBot)
"""

import sys
from unittest.mock import MagicMock, patch


class MockCdkStack:
    """Mock base class cho aws_cdk.Stack để test logic của CoreApiStack."""
    def __init__(self, scope=None, construct_id=None, **kwargs):
        self.scope = scope
        self.construct_id = construct_id
        self.region = "ap-southeast-2"
        self.account = "640737808081"


def test_core_api_stack_instantiation_with_user_pool():
    """Kiểm tra khởi tạo CoreApiStack khi truyền UserPool trực tiếp từ AuthStack."""
    mock_cdk = MagicMock()
    mock_cdk.Stack = MockCdkStack
    mock_constructs = MagicMock()

    modules_to_mock = {
        "aws_cdk": mock_cdk,
        "aws_cdk.aws_apigateway": mock_cdk.aws_apigateway,
        "aws_cdk.aws_cognito": mock_cdk.aws_cognito,
        "aws_cdk.aws_iam": mock_cdk.aws_iam,
        "aws_cdk.aws_lambda": mock_cdk.aws_lambda,
        "constructs": mock_constructs,
    }

    with patch.dict(sys.modules, modules_to_mock):
        if "infrastructure.stacks.core_api_stack" in sys.modules:
            del sys.modules["infrastructure.stacks.core_api_stack"]

        from infrastructure.stacks.core_api_stack import CoreApiStack

        mock_app = MagicMock()
        mock_user_pool = MagicMock()

        stack = CoreApiStack(mock_app, "TestCoreApiStack", user_pool=mock_user_pool)

        # 1. Kiểm tra User Pool được liên kết
        assert stack.user_pool == mock_user_pool

        # 2. Kiểm tra Cognito Authorizer được cấu hình
        assert stack.authorizer is not None
        mock_cdk.aws_apigateway.CognitoUserPoolsAuthorizer.assert_called_once()
        auth_call_kwargs = mock_cdk.aws_apigateway.CognitoUserPoolsAuthorizer.call_args[1]
        assert auth_call_kwargs["cognito_user_pools"] == [mock_user_pool]
        assert auth_call_kwargs["identity_source"] == "method.request.header.Authorization"

        # 3. Kiểm tra RestApi được tạo với CORS
        mock_cdk.aws_apigateway.RestApi.assert_called_once()
        api_kwargs = mock_cdk.aws_apigateway.RestApi.call_args[1]
        assert api_kwargs["rest_api_name"] == "SatiBot-CoreApi"
        assert "default_cors_preflight_options" in api_kwargs

        # 4. Kiểm tra các Lambda functions (chatbot, history, connector)
        assert mock_cdk.aws_lambda.Function.call_count >= 3

        # 5. Kiểm tra các resource endpoints được gắn authorizer
        # root.add_resource được gọi cho: chat, confirm, history, connect
        assert stack.api.root.add_resource.call_count == 4
        resources_created = [call[0][0] for call in stack.api.root.add_resource.call_args_list]
        assert "chat" in resources_created
        assert "confirm" in resources_created
        assert "history" in resources_created
        assert "connect" in resources_created

        # 6. Kiểm tra CfnOutput
        assert mock_cdk.CfnOutput.call_count >= 3


def test_core_api_stack_fallback_import_user_pool():
    """Kiểm tra CoreApiStack tự động import UserPool từ CloudFormation Export khi không truyền user_pool."""
    mock_cdk = MagicMock()
    mock_cdk.Stack = MockCdkStack
    mock_cdk.Fn.import_value.return_value = "imported-pool-id-1234"
    mock_constructs = MagicMock()

    modules_to_mock = {
        "aws_cdk": mock_cdk,
        "aws_cdk.aws_apigateway": mock_cdk.aws_apigateway,
        "aws_cdk.aws_cognito": mock_cdk.aws_cognito,
        "aws_cdk.aws_iam": mock_cdk.aws_iam,
        "aws_cdk.aws_lambda": mock_cdk.aws_lambda,
        "constructs": mock_constructs,
    }

    with patch.dict(sys.modules, modules_to_mock):
        if "infrastructure.stacks.core_api_stack" in sys.modules:
            del sys.modules["infrastructure.stacks.core_api_stack"]

        from infrastructure.stacks.core_api_stack import CoreApiStack

        mock_app = MagicMock()
        stack = CoreApiStack(mock_app, "TestCoreApiStackNoPool")

        mock_cdk.Fn.import_value.assert_called_with("SatiBot-UserPoolId")
        mock_cdk.aws_cognito.UserPool.from_user_pool_id.assert_called_once()
