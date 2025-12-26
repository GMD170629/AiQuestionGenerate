#!/bin/bash
# 开发环境启动脚本
# 使用 profiles 方式启动开发环境服务，如果没有指定 profile 则默认启动开发环境

if [ -z "$COMPOSE_PROFILES" ]; then
  docker-compose --profile dev "$@"
else
  docker-compose "$@"
fi

