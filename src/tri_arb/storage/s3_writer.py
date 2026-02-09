"""S3 Writer - 本地文件缓冲 + 按小时上传到 S3.

将 WebSocket 接收到的数据按小时写入本地 JSONL 文件，
后台定时将已完成的小时文件上传到 S3，上传成功后删除本地文件。

S3 路径格式:
    s3://{bucket}/{prefix}/{account_id}/{data_type}/date=YYYY-MM-DD/hour=HH.jsonl

本地路径格式:
    {local_dir}/{account_id}/{data_type}/{YYYY-MM-DD_HH}.jsonl
"""

import gzip
import json
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, TextIO

from aiobotocore.session import get_session

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class S3Writer:
    """本地文件缓冲 + 按小时上传到 S3.

    核心设计:
    - write() 同步写本地文件，微秒级完成，内部 try-except 绝不影响调用方
    - 后台 asyncio task 定时检查并上传已完成的小时文件
    - 上传成功后删除本地文件
    - flush_and_stop() 关闭时上传所有剩余文件
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "xt-websocket-data",
        account_id: Optional[str] = None,
        local_dir: str = "/tmp/xt-ws-data",
        region: str = "ap-southeast-1",
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        upload_check_interval: int = 60,
    ):
        """初始化 S3Writer.

        Args:
            bucket: S3 桶名
            prefix: S3 前缀路径
            account_id: 账号 ID（用于路径区分）
            local_dir: 本地缓冲目录
            region: AWS 区域
            aws_access_key: AWS Access Key（可选，None 则使用 IAM Role）
            aws_secret_key: AWS Secret Key（可选）
            upload_check_interval: 上传检查间隔（秒）
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.account_id = account_id or "default"
        self.region = region
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.upload_check_interval = upload_check_interval

        # 本地目录: {local_dir}/{account_id}/
        self.local_dir = Path(local_dir) / self.account_id
        self.local_dir.mkdir(parents=True, exist_ok=True)

        # 文件句柄管理
        self._file_handles: dict[str, TextIO] = {}
        self._current_hours: dict[str, str] = {}
        self._write_counts: dict[str, int] = {}

        # 上传任务
        self._upload_task: Optional[asyncio.Task[None]] = None
        self._is_running = False

        # 统计
        self._upload_stats = {
            "total_uploads": 0,
            "total_failures": 0,
            "total_records_uploaded": 0,
        }

    # ========================================
    # 小时 key 和路径
    # ========================================

    @staticmethod
    def _current_hour_key() -> str:
        """获取当前 UTC 小时 key，格式: '2026-02-09_14'"""
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d_%H")

    def _local_path(self, data_type: str, hour_key: str) -> Path:
        """本地文件路径: {local_dir}/{account_id}/{data_type}/{hour_key}.jsonl"""
        return self.local_dir / data_type / f"{hour_key}.jsonl"

    def _s3_key(self, data_type: str, hour_key: str) -> str:
        """S3 对象键: {prefix}/{account_id}/{data_type}/date=YYYY-MM-DD/hour=HH.jsonl.gz"""
        date_str, hour_str = hour_key.split("_")
        return (
            f"{self.prefix}/{self.account_id}/{data_type}/"
            f"date={date_str}/hour={hour_str}.jsonl.gz"
        )

    # ========================================
    # 写入本地文件（同步，极快）
    # ========================================

    def write(self, data_type: str, record: dict[str, Any]) -> None:
        """写入一条记录到本地 JSONL 文件。

        同步操作，直接 append 到文件，微秒级完成。
        内部捕获所有异常，绝不影响调用方（DB 入队等）。

        Args:
            data_type: 数据类型 (trades/orders/positions/accounts)
            record: 要保存的数据字典
        """
        try:
            hour = self._current_hour_key()

            # 小时切换时关闭旧文件句柄
            if self._current_hours.get(data_type) != hour:
                self._close_file(data_type)
                self._current_hours[data_type] = hour

            # 获取或打开文件
            if data_type not in self._file_handles:
                path = self._local_path(data_type, hour)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._file_handles[data_type] = open(path, "a", encoding="utf-8")
                self._write_counts[data_type] = 0

            # 写入一行 JSON
            line = json.dumps(record, cls=DecimalEncoder, ensure_ascii=False)
            self._file_handles[data_type].write(line + "\n")

            # 更新计数
            self._write_counts[data_type] = self._write_counts.get(data_type, 0) + 1
        except Exception as e:
            logger.error(f"S3Writer: 本地写入失败 ({data_type}): {e}")

    def write_batch(self, data_type: str, records: list[dict[str, Any]]) -> None:
        """批量写入多条记录。"""
        for record in records:
            self.write(data_type, record)

    def _close_file(self, data_type: str) -> None:
        """关闭指定数据类型的文件句柄。"""
        fh = self._file_handles.pop(data_type, None)
        if fh:
            try:
                fh.flush()
                fh.close()
            except Exception as e:
                logger.warning(f"S3Writer: 关闭文件失败 ({data_type}): {e}")

    # ========================================
    # 后台上传循环
    # ========================================

    async def start(self) -> None:
        """启动后台上传任务。"""
        if self._is_running:
            return
        self._is_running = True
        self._upload_task = asyncio.create_task(self._upload_loop())
        logger.info(
            f"S3Writer: Upload loop started → s3://{self.bucket}/{self.prefix}/{self.account_id}/"
        )

    async def _upload_loop(self) -> None:
        """后台循环：定时检查并上传已完成的小时文件。"""
        while self._is_running:
            try:
                await asyncio.sleep(self.upload_check_interval)
                await self._upload_old_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"S3Writer: Upload loop error: {e}")

    async def _upload_old_files(self) -> None:
        """上传所有非当前小时的文件。"""
        current_hour = self._current_hour_key()

        for data_type_dir in self.local_dir.iterdir():
            if not data_type_dir.is_dir():
                continue
            data_type = data_type_dir.name

            for file_path in data_type_dir.glob("*.jsonl"):
                hour_key = file_path.stem
                # 只上传已完成的小时文件（不是当前小时）
                if hour_key == current_hour:
                    continue

                s3_key = self._s3_key(data_type, hour_key)
                if await self._upload_file(file_path, s3_key):
                    # 上传成功，删除本地文件
                    try:
                        file_path.unlink()
                    except OSError as e:
                        logger.warning(
                            f"S3Writer: Failed to delete local file {file_path}: {e}"
                        )

    async def _upload_file(self, local_path: Path, s3_key: str) -> bool:
        """上传单个文件到 S3。

        Returns:
            True 上传成功, False 上传失败
        """
        try:
            raw_body = local_path.read_bytes()
            raw_size_kb = len(raw_body) / 1024
            line_count = raw_body.count(b"\n")

            # gzip 压缩
            compressed_body = gzip.compress(raw_body, compresslevel=6)
            compressed_size_kb = len(compressed_body) / 1024
            ratio = (1 - compressed_size_kb / raw_size_kb) * 100 if raw_size_kb > 0 else 0

            session = get_session()
            async with session.create_client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
            ) as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=compressed_body,
                    ContentType="application/x-ndjson",
                    ContentEncoding="gzip",
                )

            self._upload_stats["total_uploads"] += 1
            self._upload_stats["total_records_uploaded"] += line_count
            logger.info(
                f"S3Writer: ✅ Uploaded {line_count} records "
                f"({raw_size_kb:.1f}KB → {compressed_size_kb:.1f}KB, "
                f"gzip -{ratio:.0f}%) → s3://{self.bucket}/{s3_key}"
            )
            return True

        except Exception as e:
            self._upload_stats["total_failures"] += 1
            logger.error(f"S3Writer: ❌ Upload failed {s3_key}: {e}")
            return False

    # ========================================
    # 停止与清理
    # ========================================

    async def flush_and_stop(self) -> None:
        """关闭所有文件，上传剩余数据，停止后台任务。"""
        if not self._is_running:
            return
        self._is_running = False
        logger.info("S3Writer: Flushing and stopping...")

        # 1. 关闭所有文件句柄
        for dt in list(self._file_handles.keys()):
            self._close_file(dt)

        # 2. 取消上传循环
        if self._upload_task:
            self._upload_task.cancel()
            try:
                await self._upload_task
            except asyncio.CancelledError:
                pass

        # 3. 上传所有剩余文件（包括当前小时的）
        for data_type_dir in self.local_dir.iterdir():
            if not data_type_dir.is_dir():
                continue
            for file_path in data_type_dir.glob("*.jsonl"):
                s3_key = self._s3_key(data_type_dir.name, file_path.stem)
                await self._upload_file(file_path, s3_key)
                # 上传后删除
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError as e:
                        logger.warning(
                            f"S3Writer: Failed to delete local file {file_path} "
                            f"after final upload: {e}"
                        )

        logger.info(
            f"S3Writer: Stopped. Stats: "
            f"uploads={self._upload_stats['total_uploads']}, "
            f"records={self._upload_stats['total_records_uploaded']}, "
            f"failures={self._upload_stats['total_failures']}"
        )

    # ========================================
    # 统计信息
    # ========================================

    def get_stats(self) -> dict[str, Any]:
        """获取写入和上传统计。"""
        active_files = []
        for data_type, _fh in self._file_handles.items():
            hour = self._current_hours.get(data_type, "unknown")
            path = self._local_path(data_type, hour)
            count = self._write_counts.get(data_type, 0)
            active_files.append(f"  📄 {path} ({count} records)")

        return {
            "write_counts": dict(self._write_counts),
            "upload_stats": dict(self._upload_stats),
            "active_files": active_files,
            "current_hours": dict(self._current_hours),
        }
