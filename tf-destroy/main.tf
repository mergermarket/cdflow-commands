provider "aws" {
  region = "${var.aws_region}"
}

variable "aws_region" {
  description = "The AWS region to destroy resources in."
}

