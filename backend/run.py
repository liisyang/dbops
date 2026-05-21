"""
应用入口文件。

当前阶段先只启动 FastAPI，Celery worker 的启动代码保留但暂时注释掉，
后续任务模块补齐后可以直接恢复使用。
"""
import os
import subprocess
import time

from app.main import create_app


def _celery_pool_args():
    """
    当前环境的 Python 缺少 _ctypes 时，prefork 池无法启动。
    退回到 solo 池可以让 worker 继续运行，不影响主服务启动。
    """
    try:
        import ctypes  # noqa: F401
    except Exception:
        return ["--pool=solo"]
    return ["--pool=prefork", "--concurrency=4"]


def start_celery_worker():
    """
    在后台启动 Celery worker 监听异步任务队列。
    使用子进程启动，保持与主进程隔离。
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(os.path.dirname(project_dir), ".venv")
    worker_cmd = [
        os.path.join(venv_dir, "bin", "celery"),
        "-A",
        "app.tasks.queue",
        "worker",
        "--loglevel=info",
    ] + _celery_pool_args()

    worker_process = subprocess.Popen(
        worker_cmd,
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )

    print(f"[Celery Worker] Started with PID {worker_process.pid}")
    time.sleep(2)

    if worker_process.poll() is not None:
        stdout, stderr = worker_process.communicate()
        print(f"[Celery Worker] Failed to start: {stderr.decode()}")
        return None

    return worker_process


def main():
    """启动应用：当前只启动 FastAPI 服务。"""
    # 任务模块还没正式启用，先把 worker 注释掉，后续恢复时取消下面这段即可。
    # print("[ACC Manager] Starting Celery worker...")
    # worker_process = start_celery_worker()
    # if not worker_process:
    #     print("[ACC Manager] Warning: Celery worker failed to start, tasks may not execute!")
    # else:
    #     print("[ACC Manager] Celery worker ready")
    worker_process = None

    # 仅启动 FastAPI 服务
    app = create_app()
    print("[ACC Manager] Starting FastAPI server on http://0.0.0.0:60801")

    import uvicorn

    try:
        uvicorn.run(app, host="0.0.0.0", port=60801)
    finally:
        # 当前 worker 不启用，这里保留退出清理逻辑，后续恢复 worker 时无需再改。
        if worker_process:
            print("[ACC Manager] Shutting down Celery worker...")
            worker_process.terminate()
            worker_process.wait(timeout=5)


if __name__ == "__main__":
    main()
