#!/bin/bash
# 生产环境启动脚本
# 使用 profiles 方式启动生产环境服务

docker-compose --profile prod "$@"

