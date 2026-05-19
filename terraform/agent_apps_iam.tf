resource "aws_iam_policy" "agent_sandbox_billing_read" {
  count = var.enable_agent_sandbox_billing_irsa ? 1 : 0

  name = "${var.project_name}-agent-sandbox-billing-read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "ce:GetDimensionValues",
          "ce:GetTags",
          "pricing:GetProducts"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "agent_sandbox_billing" {
  count = var.enable_agent_sandbox_billing_irsa ? 1 : 0

  name = "${var.project_name}-agent-sandbox-billing-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Federated = aws_iam_openid_connect_provider.eks.arn
        }

        Action = "sts:AssumeRoleWithWebIdentity"

        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:${var.agent_sandbox_namespace}:${var.agent_sandbox_service_account_name}"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "agent_sandbox_billing_attach" {
  count = var.enable_agent_sandbox_billing_irsa ? 1 : 0

  role       = aws_iam_role.agent_sandbox_billing[0].name
  policy_arn = aws_iam_policy.agent_sandbox_billing_read[0].arn
}
