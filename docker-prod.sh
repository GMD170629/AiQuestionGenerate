#!/bin/bash
# 生产环境启动脚本

docker-compose -f docker-compose.yml -f docker-compose.prod.yml "$@"

