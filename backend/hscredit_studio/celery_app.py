"""Celery 应用配置."""

from celery import Celery

from hscredit_studio.core.config import settings

# 创建 Celery 实例
celery_app = Celery(
    "hscredit_studio",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "hscredit_studio.executor.tasks",
        "hscredit_studio.nodes.data_ingest",
        "hscredit_studio.nodes.eda",
        # ... 其他节点模块
    ],
)

# 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="nodes-general",
    task_routes={
        "hscredit_studio.executor.tasks.run_node": {"queue": "nodes-general"},
        "hscredit_studio.executor.tasks.run_heavy_node": {"queue": "nodes-heavy"},
    },
    broker_connection_retry_on_startup=True,
)
