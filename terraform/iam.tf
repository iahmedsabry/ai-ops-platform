# Get EKS cluster info
data "aws_eks_cluster" "this" {
  name = "${var.project_name}-eks"  # your EKS cluster name
}

# Get authentication data (used for OIDC)
data "aws_eks_cluster_auth" "this" {
  name = "${var.project_name}-eks"
}

# Create OIDC provider
resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list = ["sts.amazonaws.com"]  # required for IRSA

  thumbprint_list = ["9e99a48a9960b14926bb7f3b02e22da0afd40e6e"]
  # AWS root CA thumbprint (standard value)

  url = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
  # This gets OIDC URL from your cluster
}

# Load policy from file
data "local_file" "alb_policy" {
  filename = "${path.module}/iam_policy_alb.json"
}

# Create IAM policy
resource "aws_iam_policy" "alb_controller" {
  name   = "AWSLoadBalancerControllerPolicy"
  policy = data.local_file.alb_policy.content
}

# Get current AWS account ID
data "aws_caller_identity" "current" {}

# IAM Role for ALB Controller (IRSA)
resource "aws_iam_role" "alb_controller" {
  name = "AmazonEKSLoadBalancerControllerRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Federated = aws_iam_openid_connect_provider.eks.arn
          # This connects IAM role to your EKS OIDC provider
        }

        Action = "sts:AssumeRoleWithWebIdentity"

        Condition = {
          StringEquals = {
            # This ensures only the correct ServiceAccount can assume the role
            "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
          }
        }
      }
    ]
  })
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "alb_attach" {
  role       = aws_iam_role.alb_controller.name
  policy_arn = aws_iam_policy.alb_controller.arn
}