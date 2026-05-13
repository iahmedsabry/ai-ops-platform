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