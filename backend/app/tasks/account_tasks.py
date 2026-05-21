"""
Celery 任务函数 - 用户操作（add_user, chpasswd, check_user）。
所有任务通过 ansible-runner 执行，状态存储在 Redis，实时输出通过 Redis pub/sub 广播。
"""
import json
import os
import tempfile
import shutil
from datetime import datetime

import ansible_runner
import paramiko
import shlex
import redis as redis_lib
from celery import Task

from app.config import get_settings
from app.tasks.queue import app as celery_app
from app.models.task import TaskState
from app.models import db, Server as Host

_settings = get_settings()
from app.ansible.inventory import build_inventory


# Redis pub/sub channel for real-time output
PUBSUB_CHANNEL = "task_output"


def _get_redis_pubsub():
    """获取 Redis pubsub 连接"""
    return redis_lib.from_url(_settings.REDIS_URL)


def _emit_output(socket_id: str, event: str, data: dict):
    """通过 Redis pub/sub 发送消息到指定 socket_id room"""
    try:
        pubsub = _get_redis_pubsub()
        message = json.dumps({"socket_id": socket_id, "event": event, "data": data})
        pubsub.publish(PUBSUB_CHANNEL, message)
        pubsub.close()
    except Exception as e:
        print(f"[_emit_output] error: {e}")


def _get_ssh_creds():
    """获取 SSH 凭据"""
    ssh_user = _settings.SSH_USER
    ssh_key = _settings.SSH_KEY
    if ssh_key:
        ssh_key = os.path.expanduser(ssh_key)
    return ssh_user, ssh_key


def _get_flask_app():
    """获取 Flask app 实例（供任务使用）"""
    from app.main import get_flask_app
    app = get_flask_app()
    if app is None:
        from app.main import _init_flask_app
        app = _init_flask_app()
    return app


@celery_app.task(bind=True)
def add_user_task(self, task_id, host_ips, username, profile, password_hash, initiated_by, socket_id=None):
    """在目标主机上新增 Linux 用户（Ansible 模式）。"""
    app = _get_flask_app()
    with app.app_context():
        redis_conn = redis_lib.from_url(_settings.REDIS_URL)

        state = TaskState(
            task_id=task_id,
            status="running",
            total_hosts=len(host_ips),
            completed_hosts=0,
            started_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            results={},
            initiated_by=initiated_by,
        )
        state.save(redis_conn)

        if socket_id:
            _emit_output(socket_id, "output", {"message": f"[{task_id}] Starting on {len(host_ips)} hosts...\n"})

        hosts = Host.query.filter(Host.ip.in_(host_ips)).all()
        if not hosts:
            state.status = "failed"
            state.save(redis_conn)
            return state.to_dict()

        ssh_user, ssh_key = _get_ssh_creds()
        inventory = build_inventory(hosts, ssh_user, ssh_key)

        priv_dir = tempfile.mkdtemp()
        playbook_path = os.path.join(
            os.path.dirname(__file__), "..", "ansible", "playbooks", "add_user.yml"
        )
        playbook_path = os.path.abspath(playbook_path)

        extra_vars = {
            "username": username,
            "password_hash": password_hash,
            "group": _settings.SSH_USER_GROUP,
            "home_prefix": _settings.SSH_USER_HOME_PREFIX,
            "shell": "/bin/ksh",
            "profile": f"{_settings.SSH_PROFILE_PATH}/{profile}",
        }

        try:
            if socket_id:
                _emit_output(socket_id, "output", {"message": f"[*] 正在添加用户 {username} 到 {len(host_ips)} 台主机\n"})
                _emit_output(socket_id, "output", {"message": f"    -> profile: {profile}\n"})
                _emit_output(socket_id, "output", {"message": f"    -> 执行 playbook: add_user.yml\n"})

            runner = ansible_runner.run(
                private_data_dir=priv_dir,
                playbook=playbook_path,
                inventory=inventory,
                extravars=extra_vars,
                settings={
                    "forks": min(_settings.ANSIBLE_FORKS, len(hosts)),
                    "timeout": _settings.ANSIBLE_TIMEOUT,
                    "quiet_stdout": False,
                    "become_enabled": True,
                },
            )

            for event in runner.events:
                event_data = event.get("event_data", {})
                host = event_data.get("host", "")
                event_type = event.get("event", "")

                if event_type == "runner_on_ok" and host:
                    stdout = event_data.get("res", {}).get("stdout", "")
                    stderr = event_data.get("res", {}).get("stderr", "")
                    rc = event_data.get("res", {}).get("rc", 0)

                    state.results[host] = {
                        "status": "ok" if rc == 0 else "failed",
                        "stdout": stdout,
                        "stderr": stderr,
                    }
                    state.completed_hosts += 1
                    state.save(redis_conn)

                    if socket_id:
                        _emit_output(socket_id, "output", {"message": f"  {host}: OK (rc={rc})\n"})

                elif event_type == "runner_on_failed" and host:
                    stderr = event_data.get("res", {}).get("stderr", "")
                    state.results[host] = {"status": "failed", "stdout": "", "stderr": stderr}
                    state.completed_hosts += 1
                    state.save(redis_conn)

                    if socket_id:
                        _emit_output(socket_id, "output", {"message": f"  {host}: FAILED\n"})

            state.status = "complete"
            state.save(redis_conn)

            if socket_id:
                _emit_output(socket_id, "output", {"message": f"\n[{task_id}] Completed.\n"})

        except Exception as e:
            import traceback
            traceback.print_exc()
            state.status = "failed"
            state.save(redis_conn)
            if socket_id:
                _emit_output(socket_id, "output", {"message": f"[{task_id}] ERROR: {e}\n"})

        finally:
            shutil.rmtree(priv_dir, ignore_errors=True)

    return state.to_dict()


@celery_app.task(bind=True)
def chpasswd_task(self, task_id, host_ips, username, password_hash, initiated_by, socket_id=None):
    """在目标主机上修改用户密码（Ansible 模式）。"""
    app = _get_flask_app()
    with app.app_context():
        redis_conn = redis_lib.from_url(_settings.REDIS_URL)

        state = TaskState(
            task_id=task_id,
            status="running",
            total_hosts=len(host_ips),
            completed_hosts=0,
            started_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            results={},
            initiated_by=initiated_by,
        )
        state.save(redis_conn)

        if socket_id:
            _emit_output(socket_id, "output", {"message": f"[{task_id}] Changing password on {len(host_ips)} hosts...\n"})

        hosts = Host.query.filter(Host.ip.in_(host_ips)).all()
        if not hosts:
            state.status = "failed"
            state.save(redis_conn)
            return state.to_dict()

        ssh_user, ssh_key = _get_ssh_creds()
        inventory = build_inventory(hosts, ssh_user, ssh_key)

    priv_dir = tempfile.mkdtemp()
    playbook_path = os.path.join(
        os.path.dirname(__file__), "..", "ansible", "playbooks", "chpasswd.yml"
    )
    playbook_path = os.path.abspath(playbook_path)

    extra_vars = {"username": username, "password_hash": password_hash}

    try:
        runner = ansible_runner.run(
            private_data_dir=priv_dir,
            playbook=playbook_path,
            inventory=inventory,
            extravars=extra_vars,
            settings={
                "forks": min(_settings.ANSIBLE_FORKS, len(hosts)),
                "timeout": _settings.ANSIBLE_TIMEOUT,
                "quiet_stdout": False,
                "become_enabled": True,
            },
        )

        app = _get_flask_app()
        with app.app_context():
            redis_conn = redis_lib.from_url(_settings.REDIS_URL)
            for event in runner.events:
                event_data = event.get("event_data", {})
                host = event_data.get("host", "")
                event_type = event.get("event", "")

                if event_type == "runner_on_ok" and host:
                    rc = event_data.get("res", {}).get("rc", 0)
                    state.results[host] = {"status": "ok" if rc == 0 else "failed", "stdout": "", "stderr": ""}
                    state.completed_hosts += 1
                    state.save(redis_conn)
                    if socket_id:
                        _emit_output(socket_id, "output", {"message": f"  {host}: {'OK' if rc == 0 else 'FAILED'}\n"})

                elif event_type == "runner_on_failed" and host:
                    state.results[host] = {"status": "failed", "stdout": "", "stderr": event_data.get("res", {}).get("stderr", "")}
                    state.completed_hosts += 1
                    state.save(redis_conn)
                    if socket_id:
                        _emit_output(socket_id, "output", {"message": f"  {host}: FAILED\n"})

            state.status = "complete"
            state.save(redis_conn)

            if socket_id:
                _emit_output(socket_id, "output", {"message": f"\n[{task_id}] Completed.\n"})

    except Exception as e:
        app = _get_flask_app()
        with app.app_context():
            redis_conn = redis_lib.from_url(_settings.REDIS_URL)
            state.status = "failed"
            state.save(redis_conn)
            if socket_id:
                _emit_output(socket_id, "output", {"message": f"[{task_id}] ERROR: {e}\n"})

    finally:
        shutil.rmtree(priv_dir, ignore_errors=True)

    return state.to_dict()


@celery_app.task(bind=True)
def check_user_task(self, task_id, usernames, host_ips, initiated_by, socket_id=None):
    """在目标主机上检查用户是否存在（Paramiko 同步模式，通过 Redis pub/sub 实时输出）。"""
    print(f"[check_user_task] STARTING task_id={task_id}, usernames={usernames}, host_ips={host_ips}", flush=True)

    app = _get_flask_app()
    with app.app_context():
        redis_conn = redis_lib.from_url(_settings.REDIS_URL)

        state = TaskState(
            task_id=task_id,
            status="running",
            total_hosts=len(host_ips) * len(usernames),
            completed_hosts=0,
            started_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            results={},
            initiated_by=initiated_by,
        )
        state.save(redis_conn)

        ssh_user, ssh_key = _get_ssh_creds()

        def output_callback(msg):
            print(f"[check_user_task] output to room {socket_id}: {msg[:60]}")
            _emit_output(socket_id, "output", {"message": msg})

        output_callback(f"[CHECK] Starting check on {len(host_ips)} hosts for {len(usernames)} user(s)\n")

        for username in usernames:
            q_user = shlex.quote(username)
            home_path = f"{_settings.SSH_USER_HOME_PREFIX}/{username}"
            q_home = shlex.quote(home_path)

            for ip in host_ips:
                try:
                    output_callback(f"[*] 正在连接 {ip} ...\n")
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    if ssh_key:
                        client.connect(ip, username=ssh_user, key_filename=ssh_key, timeout=5, banner_timeout=5)
                    else:
                        client.connect(ip, username=ssh_user, password=_settings.SSH_PASSWORD, timeout=5, banner_timeout=5)

                    output_callback(f"    -> SSH 连接成功，用户: {ssh_user}\n")

                    output_callback(f"    -> 执行命令: id {q_user}\n")
                    stdin, stdout, stderr = client.exec_command(f"id {q_user}")
                    stdout.read().decode().strip()
                    user_rc = stdout.channel.recv_exit_status()
                    output_callback(f"    -> 返回码: {user_rc}\n")

                    output_callback(f"    -> 执行命令: test -d {q_home}\n")
                    stdin2, stdout2, stderr2 = client.exec_command(f"test -d {q_home}")
                    home_rc = stdout2.channel.recv_exit_status()
                    output_callback(f"    -> 返回码: {home_rc}\n")

                    client.close()

                    if user_rc == 0 and home_rc == 0:
                        result_msg = f"{username} 存在，{home_path} 存在"
                    elif user_rc == 0:
                        result_msg = f"{username} 存在，{home_path} 不存在"
                    elif home_rc == 0:
                        result_msg = f"{username} 不存在，{home_path} 存在"
                    else:
                        result_msg = f"{username} 不存在，{home_path} 不存在，可新增"

                    output_callback(f"  {ip}: {result_msg}\n")

                    key = f"{ip}:{username}"
                    state.results[key] = {"status": "ok", "stdout": result_msg, "stderr": ""}
                    state.completed_hosts += 1
                    state.save(redis_conn)

                except Exception as e:
                    output_callback(f"  {ip}: SSH连接失败 - {str(e)}\n")
                    key = f"{ip}:{username}"
                    state.results[key] = {"status": "failed", "stdout": "", "stderr": str(e)}
                    state.completed_hosts += 1
                    state.save(redis_conn)

        output_callback(f"\n[CHECK] Check completed.\n")

        state.status = "complete"
        state.save(redis_conn)

    print(f"[check_user_task] COMPLETED task_id={task_id}", flush=True)
    return {"task_id": task_id, "usernames": usernames, "host_ips": host_ips}
