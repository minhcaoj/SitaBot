"""
Unit tests cho AWS CDK AuthStack (Cognito UserPool, Web Client, Trigger, User Groups).
Author: Nguyễn Đức Huy (Nhóm 10 - SatiBot)
"""

import sys
from unittest.mock import MagicMock, patch


class MockCdkStack:
    """Mock base class cho aws_cdk.Stack để test logic của AuthStack."""
    def __init__(self, scope=None, construct_id=None, **kwargs):
        self.scope = scope
        self.construct_id = construct_id
        self.region = "ap-southeast-2"
        self.account = "640737808081"


def test_auth_stack_instantiation():
    """Kiểm tra logic khởi tạo toàn diện của AuthStack."""
    mock_cdk = MagicMock()
    mock_cdk.Stack = MockCdkStack
    mock_constructs = MagicMock()

    modules_to_mock = {
        "aws_cdk": mock_cdk,
        "aws_cdk.aws_cognito": mock_cdk.aws_cognito,
        "aws_cdk.aws_iam": mock_cdk.aws_iam,
        "aws_cdk.aws_lambda": mock_cdk.aws_lambda,
        "constructs": mock_constructs,
    }

    with patch.dict(sys.modules, modules_to_mock):
        if "infrastructure.stacks.auth_stack" in sys.modules:
            del sys.modules["infrastructure.stacks.auth_stack"]

        from infrastructure.stacks.auth_stack import AuthStack

        mock_app = MagicMock()
        stack = AuthStack(mock_app, "TestAuthStack", users_table_name="Test-Users-Table")

        # 1. Kiểm tra cấu hình bảng DynamoDB
        assert stack.users_table_name == "Test-Users-Table"

        # 2. Kiểm tra Lambda Trigger được khởi tạo
        assert stack.post_confirmation_fn is not None
        mock_cdk.aws_lambda.Function.assert_called_once()
        lambda_call_kwargs = mock_cdk.aws_lambda.Function.call_args[1]
        assert lambda_call_kwargs["function_name"] == "SatiBot-CognitoPostConfirmation"
        assert lambda_call_kwargs["handler"] == "functions.auth_handler.index.lambda_handler"
        assert lambda_call_kwargs["environment"]["USERS_TABLE_NAME"] == "Test-Users-Table"

        # 3. Kiểm tra IAM Policy cấp quyền DynamoDB
        stack.post_confirmation_fn.add_to_role_policy.assert_called_once()

        # 4. Kiểm tra Cognito User Pool
        mock_cdk.aws_cognito.UserPool.assert_called_once()
        user_pool_kwargs = mock_cdk.aws_cognito.UserPool.call_args[1]
        assert user_pool_kwargs["user_pool_name"] == "SatiBot-UserPool"
        assert user_pool_kwargs["self_sign_up_enabled"] is True

        # 5. Kiểm tra Cognito Web Client (generate_secret=False cho SPA)
        stack.user_pool.add_client.assert_called_once()
        client_kwargs = stack.user_pool.add_client.call_args[1]
        assert client_kwargs["user_pool_client_name"] == "SatiBot-WebClient"
        assert client_kwargs["generate_secret"] is False

        # 6. Kiểm tra User Groups (admin precedence=1, user precedence=10)
        assert mock_cdk.aws_cognito.CfnUserPoolGroup.call_count == 2
        groups_created = [call[1]["group_name"] for call in mock_cdk.aws_cognito.CfnUserPoolGroup.call_args_list]
        assert "admin" in groups_created
        assert "user" in groups_created

        # 7. Kiểm tra CfnOutput (3 outputs: UserPoolId, UserPoolArn, UserPoolClientId)
        assert mock_cdk.CfnOutput.call_count >= 3
