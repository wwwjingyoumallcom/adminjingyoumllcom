scripts/import_sql.py —— SQL 导入工具

## 特性
- 自动读 .env 配置 ：从 .env.dev （或指定的 env 文件）读取 DB_* 配置，不再硬编码
- 支持 MySQL 和 PostgreSQL ：根据 DB_TYPE 自动选择 asyncmy 或 asyncpg 驱动
- 强制 utf8mb4 （MySQL）：避免再次出现中文乱码
- 支持多文件 ：一次可导入多个 SQL 文件（如主 SQL + 插件种子数据）
- 自动验证 ：导入后查 sys_menu 确认中文是否正常
## 使用方法
在 ruoyi-fastapi-backend 目录下（已激活 .venv ）：


```
# 默认：读 .env.dev 配置，导入 sql/ruoyi-fastapi.sql
python scripts/import_sql.py

# 指定 env 文件和 SQL 文件
python scripts/import_sql.py --env .env.prod --sql sql/ruoyi-fastapi-pg.sql

# 同时导入多个 SQL（如主库 + 插件种子）
python scripts/import_sql.py --sql sql/ruoyi-fastapi.sql plugins/ai/seeds/mysql/ai_provider_type.sql
```

