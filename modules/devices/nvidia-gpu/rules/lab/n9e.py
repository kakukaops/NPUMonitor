"""Fixed Nightingale 9.3.0 API adapter for the isolated simulation lab only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://nightingale:17000/api/n9e'
GROUP = 'GPU模拟实验'
OWNER = 'gpu-alert-lab'


class API:
    def __init__(self, token_path='/run/secrets/n9e-token', timeout=20):
        token = Path(token_path).read_text().strip()
        if not token or '\n' in token or '\r' in token:
            raise ValueError('API Token 文件必须仅包含一行非空 token')
        self.token = token
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={'X-User-Token': self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            # Don't dump response bodies or request headers, which may contain secrets.
            raise RuntimeError(f'{method} {path}: HTTP {error.code}') from None
        if isinstance(result, dict):
            if result.get('error') or result.get('err'):
                raise RuntimeError(f'{method} {path}: API error (details omitted)')
            if 'dat' in result:
                return result['dat']
            if 'data' in result:
                return result['data']
        return result


def unique(rows, name):
    found = [row for row in (rows or []) if row['name'] == name]
    if len(found) > 1:
        raise ValueError(f'存在多个同名对象，停止避免误操作：{name}')
    return found[0] if found else None


def make_rule(item, group_id, ds_id, notify_id, version):
    digest = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {
        'name': item['name'], 'group_id': group_id, 'cate': 'prometheus', 'prod': 'metric',
        'datasource_queries': [{'match_type': 0, 'op': 'in', 'values': [ds_id]}],
        'rule_config': {'queries': [{'prom_ql': item['expression'], 'severity': item['severity'],
                                    'recover_config': item.get('recover_config', {'judge_type': 0})}]},
        'prom_eval_interval': item.get('eval_interval_seconds', 5), 'prom_for_duration': item['for_seconds'],
        'disabled': 0, 'notify_version': 1, 'notify_rule_ids': [notify_id],
        'notify_recovered': 1, 'notify_repeat_step': 60, 'notify_max_number': 3,
        'recover_duration': 0, 'note': item['note'],
        'append_tags': [f'rule_id={item["key"]}', 'simulated=true', 'managed_by=gpu-alert-lab'],
        'annotations': {'catalog_version': version, 'catalog_sha256': digest,
                        'scope': 'simulation-only', 'managed_by': OWNER},
    }


def install(api, catalog):
    # Fail before creating anything if credential isn't an administrator.
    profile = api.call('GET', '/self/profile')
    if not profile.get('admin'):
        raise ValueError('导入专用数据源需要管理员测试Token；未执行写入')
    groups = api.call('GET', '/user-groups')
    team = unique(groups, 'GPU模拟-测试用户组')
    if team is None:
        api.call('POST', '/user-groups', {'name': 'GPU模拟-测试用户组',
                 'note': 'GPU模拟实验专用，仅创建者默认加入', 'is_sync_to_flashduty': False})
        team = unique(api.call('GET', '/user-groups'), 'GPU模拟-测试用户组')
    if team is None:
        raise ValueError('测试用户组创建后回读失败')
    user_group_id = team['id']
    bg = unique(api.call('GET', '/busi-groups?all=true&limit=1000'), GROUP)
    if bg is None:
        api.call('POST', '/busi-groups', {'name': GROUP, 'members': [
            {'user_group_id': user_group_id, 'perm_flag': 'rw'}]})
        bg = unique(api.call('GET', '/busi-groups?all=true&limit=1000'), GROUP)
    if bg is None:
        raise ValueError('业务组创建后回读失败')
    ds_name = 'GPU模拟-Prometheus'
    sources = api.call('POST', '/datasource/list', {'plugin_type': 'prometheus'})
    ds = unique(sources, ds_name)
    if ds is None:
        api.call('POST', '/datasource/upsert', {
            'name': ds_name, 'identifier': 'gpu-sim-lab', 'plugin_type': 'prometheus',
            'plugin_type_name': 'Prometheus', 'category': 'timeseries', 'status': 'enabled',
            'cluster_name': 'default', 'settings': {'prometheus_cluster_name': 'default'},
            'http': {'url': 'http://prometheus:9090', 'timeout': 10000, 'dial_timeout': 3000},
            'auth': {'basic_auth': False}, 'description': 'GPU模拟实验专用，只读查询'})
        ds = unique(api.call('POST', '/datasource/list', {'plugin_type': 'prometheus'}), ds_name)
    if ds is None or ds.get('http', {}).get('url') != 'http://prometheus:9090':
        raise ValueError('专用数据源URL不符，停止，不覆盖现有配置')
    channel_name = 'GPU模拟-本地Webhook'
    channel = unique(api.call('GET', '/notify-channel-configs'), channel_name)
    endpoint = 'http://notification-receiver:9080/webhook'
    if channel is None:
        api.call('POST', '/notify-channel-configs', [{
            'name': channel_name, 'ident': 'callback', 'enable': True, 'request_type': 'http',
            'description': 'GPU模拟实验专用，仅容器内接收器',
            'request_config': {'http_request_config': {
                'url': endpoint, 'method': 'POST', 'headers': {'Content-Type': 'application/json'},
                'timeout': 5000, 'concurrency': 2, 'retry_times': 1, 'retry_interval': 100,
                'request': {'body': '{{ jsonMarshal $events }}'}}}}])
        channel = unique(api.call('GET', '/notify-channel-configs'), channel_name)
    if channel['request_config']['http_request_config']['url'] != endpoint:
        raise ValueError('通知地址不符，停止避免发送到外部')
    nr_name = 'GPU模拟-通知规则'
    nr = unique(api.call('GET', '/notify-rules'), nr_name)
    if nr is None:
        api.call('POST', '/notify-rules', [{
            'name': nr_name, 'description': 'GPU模拟实验专用', 'enable': True,
            'user_group_ids': [user_group_id], 'notify_configs': [{
                'channel_id': channel['id'], 'template_id': 0, 'params': {}, 'type': 'all',
                'severities': [1, 2, 3], 'time_ranges': [], 'label_keys': [], 'attributes': []}]}])
        nr = unique(api.call('GET', '/notify-rules'), nr_name)
    configs = nr.get('notify_configs', [])
    if (not nr.get('enable') or len(configs) != 1 or
            configs[0].get('channel_id') != channel['id']):
        raise ValueError('现有测试通知规则已修改或禁用，停止，不覆盖用户配置')
    gid = bg['id']
    existing = api.call('GET', f'/busi-group/{gid}/alert-rules')
    for item in catalog['rules']:
        desired = make_rule(item, gid, ds['id'], nr['id'], catalog['catalog_version'])
        old = unique(existing, item['name'])
        if old:
            if old.get('annotations', {}).get('managed_by') != OWNER:
                raise ValueError('同名规则并非本实验管理，停止：' + item['key'])
            print(f'保留现有规则（不覆盖修改/禁用）：{item["key"]} id={old["id"]}')
            continue
        # Each expression must parse and execute on this Prometheus before import.
        url = 'http://prometheus:9090/api/v1/query?' + urllib.parse.urlencode({'query': item['expression']})
        with api.opener.open(url, timeout=10) as response:
            if json.load(response).get('status') != 'success':
                raise ValueError('PromQL检查失败: ' + item['key'])
        result = api.call('POST', f'/busi-group/{gid}/alert-rules', [desired])
        if isinstance(result, dict) and any(result.values()):
            raise ValueError('规则创建返回错误：' + item['key'])
        reread = unique(api.call('GET', f'/busi-group/{gid}/alert-rules'), item['name'])
        if not reread:
            raise ValueError('规则创建后回读失败: ' + item['key'])
        print(f'已创建：{item["key"]} id={reread["id"]}')
    print(json.dumps({'group_id': gid, 'datasource_id': ds['id'], 'notify_rule_id': nr['id']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['import', 'inspect', 'events'])
    args = parser.parse_args()
    try:
        api = API()
        if args.action == 'import':
            install(api, json.loads(Path('/rules/lab-catalog.json').read_text()))
        else:
            bg = unique(api.call('GET', '/busi-groups?all=true&limit=1000'), GROUP)
            if not bg:
                raise ValueError('尚未导入GPU模拟业务组')
            if args.action == 'events':
                for label, endpoint in [('当前活跃告警', '/alert-cur-events/list'),
                                        ('最近24小时历史记录', '/alert-his-events/list')]:
                    data = api.call('GET', endpoint + f'?bgid={bg["id"]}&hours=24&limit=100')
                    print(f'{label}: {data["total"]}')
                    print(json.dumps([{key: row.get(key) for key in
                        ('id', 'rule_name', 'group_name', 'is_recovered', 'trigger_value',
                         'trigger_time', 'recover_time', 'tags')}
                        for row in data['list']], ensure_ascii=False, indent=2))
                return 0
            rows = api.call('GET', f'/busi-group/{bg["id"]}/alert-rules')
            print(json.dumps([{'id': r['id'], 'name': r['name'], 'disabled': r['disabled'],
                               'notify_rule_ids': r['notify_rule_ids']} for r in rows], ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
