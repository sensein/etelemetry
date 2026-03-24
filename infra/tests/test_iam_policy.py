"""Tests to validate IAM policy definitions in iam.tf.

These tests perform static analysis on the HCL file to ensure
security best practices are followed.
"""

import os
import re

IAM_TF_PATH = os.path.join(os.path.dirname(__file__), "..", "iam.tf")


def _read_iam_tf():
    with open(IAM_TF_PATH, "r") as f:
        return f.read()


def test_no_iam_wildcard_actions():
    """Deploy role must not have iam:* actions."""
    content = _read_iam_tf()
    assert "iam:*" not in content, "iam:* action found in iam.tf - this is too permissive"


def test_no_wildcard_resource_on_ssm_put():
    """ssm:PutParameter must not use Resource: '*'."""
    content = _read_iam_tf()
    # Find the SSM parameters statement block and verify it has a scoped resource
    ssm_section = re.search(
        r'(?s)"ssm:PutParameter".*?Resource\s*=\s*"([^"]+)"', content
    )
    assert ssm_section is not None, "Could not find ssm:PutParameter resource scope"
    resource = ssm_section.group(1)
    assert resource != "*", "ssm:PutParameter must not use Resource: '*'"
    assert "/etelemetry/" in resource, "ssm:PutParameter should be scoped to /etelemetry/*"


def test_no_wildcard_resource_on_ecr_put():
    """ecr:PutImage must not use Resource: '*'."""
    content = _read_iam_tf()
    # Find the ECR push statement block
    ecr_section = re.search(
        r'(?s)"ecr:PutImage".*?Resource\s*=\s*(\S+)', content
    )
    assert ecr_section is not None, "Could not find ecr:PutImage resource scope"
    resource = ecr_section.group(1)
    assert resource.strip('"') != "*", "ecr:PutImage must not use Resource: '*'"


def test_trust_policy_contains_correct_repo():
    """Trust policy must reference the correct GitHub repo."""
    content = _read_iam_tf()
    assert "repo:sensein/etelemetry:ref:refs/heads/main" in content, (
        "Trust policy must contain 'repo:sensein/etelemetry:ref:refs/heads/main'"
    )


def test_no_admin_or_power_user_access():
    """No AdministratorAccess or PowerUserAccess managed policy references."""
    content = _read_iam_tf()
    assert "AdministratorAccess" not in content, (
        "AdministratorAccess managed policy found - this is too permissive"
    )
    assert "PowerUserAccess" not in content, (
        "PowerUserAccess managed policy found - this is too permissive"
    )


def test_deploy_role_has_expected_actions():
    """Deploy role should have the expected set of actions."""
    content = _read_iam_tf()
    expected_actions = [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:GetParameter",
        "ssm:PutParameter",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
    ]
    for action in expected_actions:
        assert action in content, f"Expected action '{action}' not found in iam.tf"


if __name__ == "__main__":
    test_no_iam_wildcard_actions()
    test_no_wildcard_resource_on_ssm_put()
    test_no_wildcard_resource_on_ecr_put()
    test_trust_policy_contains_correct_repo()
    test_no_admin_or_power_user_access()
    test_deploy_role_has_expected_actions()
    print("All IAM policy tests passed.")
