"""
动态 inventory - 将 Host 模型列表转换为 ansible-runner 所需的 dict 格式。
不使用文件，直接在内存中构建。
"""


def build_inventory(hosts: list, ssh_user: str, ssh_key: str = None) -> dict:
    """
    从 Host 列表构建 ansible-runner 内存 inventory dict。

    Args:
        hosts: Host 模型列表
        ssh_user: SSH 用户名
        ssh_key: SSH 私钥路径

    Returns:
        Ansible inventory dict，格式：
        {
            'all': {
                'hosts': {
                    '10.0.0.1': {'ansible_user': 'dbaacc', ...},
                    ...
                }
            }
        }
    """
    inventory = {
        'all': {
            'hosts': {}
        }
    }

    for h in hosts:
        host_vars = {
            'ansible_user': ssh_user,
        }
        if ssh_key:
            host_vars['ansible_ssh_private_key_file'] = ssh_key

        inventory['all']['hosts'][h.ip] = host_vars

    return inventory
