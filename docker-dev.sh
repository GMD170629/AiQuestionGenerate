#!/bin/bash
# 开发环境启动脚本

docker-compose -f docker-compose.yml -f docker-compose.dev.yml "$@"

