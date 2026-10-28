variable "environment" {}
variable "vpc_cidr" {}

resource "aws_sqs_queue" "orders" {
  name = "orders-queue"
}

resource "aws_s3_bucket" "assets" {
  bucket = "acme-assets"
}
