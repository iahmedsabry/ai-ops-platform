# AWS region variable
variable "aws_region" {
  description = "AWS region to deploy resources"  # Simple explanation
  type        = string                            # Must be a string
}

variable "aws_profile" {
  description = "Optional AWS CLI profile for Terraform; leave null to use the default credential chain"
  type        = string
  default     = null
}

# Project name (used for naming resources later)
variable "project_name" {
  description = "Project name prefix"
  type        = string
}

# VPC CIDR block (main network range)
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

# Public subnet CIDRs
variable "public_subnets" {
  description = "List of public subnet CIDRs"
  type        = list(string)
}

# Private subnet CIDRs
variable "private_subnets" {
  description = "List of private subnet CIDRs"
  type        = list(string)
}

variable "enable_agent_sandbox_billing_irsa" {
  description = "Create an IAM role for the agent-sandbox ServiceAccount to read AWS billing data"
  type        = bool
  default     = true
}

variable "agent_sandbox_namespace" {
  description = "Namespace for the agent-sandbox ServiceAccount"
  type        = string
  default     = "default"
}

variable "agent_sandbox_service_account_name" {
  description = "ServiceAccount name used by the agent-sandbox deployment"
  type        = string
  default     = "agent-sandbox"
}