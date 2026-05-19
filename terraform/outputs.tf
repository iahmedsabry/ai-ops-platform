# VPC ID
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

# Public Subnet IDs
output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id  # Get all public subnet IDs
}

# Private Subnet IDs
output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id  # Get all private subnet IDs
}

output "alb_controller_role_arn" {
  value = aws_iam_role.alb_controller.arn
}

output "agent_sandbox_billing_role_arn" {
  description = "IAM role ARN to annotate on the agent-sandbox ServiceAccount for Cost Explorer access"
  value       = try(aws_iam_role.agent_sandbox_billing[0].arn, null)
}