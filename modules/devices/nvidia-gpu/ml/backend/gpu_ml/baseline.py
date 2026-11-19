"""Single-metric eligibility and reproducible simulation reference data (never a fallback)."""
import math
import statistics

PRIMARY_METRICS = ('gpu_temp', 'memory_temp', 'power', 'util', 'mem_util')
CONDITIONAL_METRICS = ('sm_clock', 'mem_clock', 'fb_used')

def sample_count(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 30:
        raise ValueError('确认/恢复样本数须为1至30的整数')
    return value

def diagnostics(rows, metric):
    if metric not in PRIMARY_METRICS + CONDITIONAL_METRICS:
        raise ValueError('该字段不支持当前连续量动态基线')
    if len(rows) < 240:
        raise ValueError('至少需要240个有效唯一源样本；长窗口可能要求更多')
    times = [r['t'] for r in rows]
    values = [r['values'][metric] for r in rows]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in times + values):
        raise ValueError('源时间和指标必须为有限数值')
    gaps = [b-a for a,b in zip(times, times[1:])]
    if min(gaps) <= 0:
        raise ValueError('源时间必须严格递增且唯一')
    cadence = statistics.median(gaps)
    train = values[:int(len(values)*.6)]
    warnings = []
    if metric in CONDITIONAL_METRICS:
        warnings.append('条件候选：需评估档位/分配阶跃，优先结合配置或负载解释')
    if len(set(train)) < 3:
        raise ValueError('训练段有效取值不足3种，不适合当前动态预测；可保留原始曲线或规则')
    if sum(v == 0 for v in values) / len(values) > .8:
        warnings.append('超过80%为合法零值；检查空闲工况与可预测性，零值不当缺失')
    return {'metric':metric, 'tier':'primary' if metric in PRIMARY_METRICS else 'conditional',
            'samples':len(rows), 'unique_values':len(set(values)), 'zero_fraction':sum(v==0 for v in values)/len(values),
            'minimum':min(values), 'maximum':max(values), 'cadence_seconds':cadence,
            'continuous_pairs':sum(abs(g-cadence)<=cadence*.25 for g in gaps),
            'gap_pairs':sum(abs(g-cadence)>cadence*.25 for g in gaps), 'warnings':warnings,
            'meaning':'input suitability only; not fault accuracy or production admission'}


def reference_rows(entity, metric, start, end, step):
    from .simulation import UUIDS, CLUSTER, healthy
    if entity not in [CLUSTER+'|'+uid for uid in UUIDS] or metric not in PRIMARY_METRICS:
        raise ValueError('参考数据仅用于显式模拟GPU的首批5项指标')
    index = UUIDS.index(entity.split('|', 1)[1])
    rows = []
    for t in range(int(start), int(end)+1, step):
        values = healthy([t], index, t+index)
        rows.append({'t':float(t), 'values':{metric:float(values[metric][0])}})
    return rows
