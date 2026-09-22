"""
SQL 文件导入工具

用途：把 sql/ruoyi-fastapi.sql（或指定 SQL 文件）导入到数据库，
     自动从 .env 文件读取数据库配置，避免硬编码。

用法（在 ruoyi-fastapi-backend 目录下，已激活 .venv）：
    # 默认导入 sql/ruoyi-fastapi.sql，读取 .env.dev 配置
    python scripts/import_sql.py

    # 指定 env 文件和 SQL 文件
    python scripts/import_sql.py --env .env.prod --sql sql/ruoyi-fastapi-pg.sql

    # 同时导入多个 SQL 文件（如插件种子数据）
    python scripts/import_sql.py --sql sql/ruoyi-fastapi.sql plugins/ai/seeds/mysql/ai_provider_type.sql

依赖：sqlparse、asyncmy（MySQL）或 asyncpg（PostgreSQL）
     安装：uv pip install sqlparse
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

# 脚本位于 scripts/，项目 backend 根目录是上一级
BACKEND_DIR = Path(__file__).resolve().parent.parent


def parse_env_file(env_path: Path) -> dict:
    """简单解析 .env 文件，提取 KEY = VALUE（去掉引号和注释）。"""
    config = {}
    if not env_path.exists():
        raise FileNotFoundError(f"env 文件不存在: {env_path}")
    pattern = re.compile(r"^\s*([A-Z_]+)\s*=\s*(.*?)\s*(?:#.*)?$")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            # 去掉首尾引号
            if (val.startswith("'") and val.endswith("'")) or (
                val.startswith('"') and val.endswith('"')
            ):
                val = val[1:-1]
            config[key] = val
    return config


def get_db_config(env_path: Path) -> dict:
    """从 env 配置中提取数据库连接参数。"""
    cfg = parse_env_file(env_path)
    required = ["DB_TYPE", "DB_HOST", "DB_PORT", "DB_USERNAME", "DB_PASSWORD", "DB_DATABASE"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"env 文件缺少数据库配置项: {missing}")
    return {
        "db_type": cfg["DB_TYPE"].lower(),
        "host": cfg["DB_HOST"],
        "port": int(cfg["DB_PORT"]),
        "user": cfg["DB_USERNAME"],
        "password": cfg["DB_PASSWORD"],
        "database": cfg["DB_DATABASE"],
    }


async def import_mysql(cfg: dict, sql_path: Path) -> None:
    import asyncmy
    import sqlparse

    conn = await asyncmy.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        db=cfg["database"],
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        cur = conn.cursor()
        await _execute_sql_file(cur, sql_path)
        await conn.commit()
        await _verify_menu_mysql(cur)
    finally:
        conn.close()


async def import_postgresql(cfg: dict, sql_path: Path) -> None:
    import asyncpg
    import sqlparse

    conn = await asyncpg.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )
    try:
        await _execute_sql_file_pg(conn, sql_path)
        await _verify_menu_pg(conn)
    finally:
        await conn.close()


async def _execute_sql_file(cur, sql_path: Path) -> None:
    """MySQL：用 sqlparse 分割后逐条 execute（asyncmy cursor）。"""
    sql_text = sql_path.read_text(encoding="utf-8")
    statements = [s.strip() for s in sqlparse.split(sql_text) if s.strip()]
    print(f"共 {len(statements)} 条语句，开始执行...")
    ok, fail = 0, 0
    for i, stmt in enumerate(statements, 1):
        try:
            await cur.execute(stmt)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(statements)}] 失败: {e}")
            print(f"  stmt: {stmt[:120]}")
    print(f"完成: 成功 {ok} 条, 失败 {fail} 条")


async def _execute_sql_file_pg(conn, sql_path: Path) -> None:
    """PostgreSQL：asyncpg 不支持多语句 execute，用 sqlparse 分割逐条执行。"""
    import sqlparse

    sql_text = sql_path.read_text(encoding="utf-8")
    statements = [s.strip() for s in sqlparse.split(sql_text) if s.strip()]
    print(f"共 {len(statements)} 条语句，开始执行...")
    ok, fail = 0, 0
    for i, stmt in enumerate(statements, 1):
        try:
            await conn.execute(stmt)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(statements)}] 失败: {e}")
            print(f"  stmt: {stmt[:120]}")
    print(f"完成: 成功 {ok} 条, 失败 {fail} 条")


async def _verify_menu_mysql(cur) -> None:
    try:
        await cur.execute("SELECT menu_id, menu_name FROM sys_menu LIMIT 5;")
        rows = await cur.fetchall()
        print("\n菜单验证 (sys_menu):")
        for row in rows:
            print("  ", row)
    except Exception as e:
        print(f"菜单验证跳过: {e}")


async def _verify_menu_pg(conn) -> None:
    try:
        rows = await conn.fetch("SELECT menu_id, menu_name FROM sys_menu LIMIT 5;")
        print("\n菜单验证 (sys_menu):")
        for row in rows:
            print("  ", tuple(row.values()))
    except Exception as e:
        print(f"菜单验证跳过: {e}")


async def main(args: argparse.Namespace) -> int:
    env_path = (BACKEND_DIR / args.env).resolve()
    sql_paths = [(BACKEND_DIR / p).resolve() for p in args.sql]

    cfg = get_db_config(env_path)
    print(f"数据库: {cfg['db_type']} @ {cfg['host']}:{cfg['port']}/{cfg['database']}")
    print(f"env 文件: {env_path}")

    for sql_path in sql_paths:
        if not sql_path.exists():
            print(f"SQL 文件不存在: {sql_path}")
            return 1
        print(f"\n=== 导入: {sql_path} ===")
        if cfg["db_type"] == "mysql":
            await import_mysql(cfg, sql_path)
        elif cfg["db_type"] in ("postgresql", "postgres", "pg"):
            await import_postgresql(cfg, sql_path)
        else:
            print(f"不支持的数据库类型: {cfg['db_type']}")
            return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把 SQL 文件导入到数据库（配置从 .env 文件读取）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env",
        default=".env.dev",
        help="env 文件路径（相对 backend 根目录），默认 .env.dev",
    )
    parser.add_argument(
        "--sql",
        nargs="+",
        default=["sql/ruoyi-fastapi.sql"],
        help="要导入的 SQL 文件路径（可多个，相对 backend 根目录），默认 sql/ruoyi-fastapi.sql",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    sys.exit(asyncio.run(main(args)))
