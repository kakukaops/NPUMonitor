#!/usr/bin/env python3
"""Build H100 maintenance, thermal and interconnect review queries and fixtures."""
import argparse
import json
from pathlib import Path
import yaml
from build_h100_ecc_xid import TARGET, DEVICES, KEY, fresh, guarded, counter_query

ROOT = Path(__file__).resolve().parents[1] / 'monitoring'
FLOAT_BLANK = 140737488355328


def sensor(field, positive=False):
    raw = f'{field}{{{TARGET},{DEVICES}}}'
    current = fresh(raw)
    valid = (f'({current} and on ({KEY}) (count by ({KEY}) ({current}) == 1)'
             f' and on (cluster_id,job,instance) ({fresh(f"up{{{TARGET}}}")} == 1)'
             f' and ({raw} < {FLOAT_BLANK}) and ({raw} > -{FLOAT_BLANK})'
             f' and (({raw} - {raw}) == 0))')
    if positive:
        valid = f'({valid} > 0)'
    return valid


def build():
    queries = []
    cases = []

    def query(query_id, inputs, expression, unit, purpose):
        queries.append({'query_id': query_id, 'inputs': inputs, 'expression': expression,
                        'unit': unit, 'purpose': purpose, 'default_policy': 'disabled'})

    def case(query_id, name, samples, expected=None, source='1+0x10', extras=None):
        rows = [{'series': f'up{{{TARGET}}}', 'values': source}]
        for field, values in samples.items():
            if values is not None:
                rows.append({'series': f'{field}{{{TARGET},UUID="GPU-FIXTURE-0000"}}', 'values': values})
        rows.extend(extras or [])
        expression = next(q['expression'] for q in queries if q['query_id'] == query_id)
        output = [] if expected is None else [
            {'labels': '{cluster_id="fixture-cluster",UUID="GPU-FIXTURE-0000"}', 'value': expected}]
        cases.append({'name': f'{query_id}.{name}', 'interval': '30s', 'input_series': rows,
                      'promql_expr_test': [{'expr': f'max by ({KEY}) ({expression})',
                                            'eval_time': '300s', 'exp_samples': output}]})

    pending = 'DCGM_FI_DEV_ROW_REMAP_PENDING'
    _, valid = guarded(pending)
    query('memory.remap_pending', [pending], f'({valid} == 1)', 'boolean', 'maintenance_review')
    for value, expected in [('0', None), ('1', 1), ('2', None), ('-1', None), ('NaN', None), ('Inf', None)]:
        case('memory.remap_pending', value, {pending: value + '+0x10'}, expected)
    case('memory.remap_pending', 'missing', {pending: None})
    case('memory.remap_pending', 'stale', {pending: '1 _ _ _ _ _ _ _ _ _ _'})

    for domain, field, limit in [
        ('gpu', 'DCGM_FI_DEV_GPU_TEMP', 'DCGM_FI_DEV_GPU_MAX_OP_TEMP'),
        ('memory', 'DCGM_FI_DEV_MEMORY_TEMP', 'DCGM_FI_DEV_MEM_MAX_OP_TEMP')]:
        query_id = f'thermal.{domain}_operating_margin'
        expression = f'({sensor(limit, positive=True)} - on ({KEY}) {sensor(field)})'
        query(query_id, [field, limit], expression, 'celsius', 'temperature_margin_dashboard')
        for name, temperature, maximum, expected in [
            ('below', '94', '95', 1), ('boundary', '95', '95', 0),
            ('above', '96', '95', -1), ('fractional', '94.5', '95', .5),
            ('negative_temperature', '-5', '95', 100), ('invalid', 'NaN', '95', None),
            ('infinity', 'Inf', '95', None), ('missing_limit', '55', None, None),
            ('zero_limit', '55', '0', None), ('negative_limit', '55', '-1', None),
            ('blank_limit', '55', str(FLOAT_BLANK), None)]:
            case(query_id, name, {field: temperature + '+0x10',
                 limit: None if maximum is None else maximum + '+0x10'}, expected)
        case(query_id, 'stale_limit', {field: '55+0x10', limit: '95 _ _ _ _ _ _ _ _ _ _'})
        case(query_id, 'source_down', {field: '55+0x10', limit: '95+0x10'}, source='0+0x10')
        case(query_id, 'duplicate_limit', {field: '55+0x10', limit: '95+0x10'}, extras=[
            {'series': f'{limit}{{{TARGET},UUID="GPU-FIXTURE-0000",replica="other"}}', 'values': '95+0x10'}])
        case(query_id, 'limit_belongs_to_other_gpu', {field: '55+0x10'}, extras=[
            {'series': f'{limit}{{{TARGET},UUID="GPU-FIXTURE-0001"}}', 'values': '95+0x10'}])

    mask = 'DCGM_FI_DEV_CLOCKS_EVENT_REASONS'
    raw, valid = guarded(mask)
    valid = f'({valid} and ({raw} < 9007199254740992))'
    bits = [('sw_thermal', 32), ('hw_thermal', 64), ('sw_power_cap', 4),
            ('hw_power_brake', 128), ('hw_slowdown', 8), ('sync_boost', 16)]
    for reason, bit in bits:
        query_id = f'clock.{reason}'
        query(query_id, [mask], f'((floor({valid} / {bit}) % 2) == 1)', 'boolean', 'clock_reason_dashboard')
        for value, expected in [(0, None), (bit, 1), (bit + 1, 1), (511, 1), (512, None), (-1, None)]:
            case(query_id, str(value), {mask: f'{value}+0x10'}, expected)
        case(query_id, 'unknown_bit_with_known_reason', {mask: f'{512 + bit}+0x10'}, 1)
        case(query_id, 'fractional_mask', {mask: f'{bit}.5+0x10'})
        case(query_id, 'nan_mask', {mask: 'NaN+0x10'})
        # Power-cap and idle flags alone cannot establish thermal slowdown.
        if reason in ('sw_thermal', 'hw_thermal'):
            case(query_id, 'power_cap_only', {mask: '4+0x10'})
            case(query_id, 'generic_hw_slowdown_only', {mask: '8+0x10'})
    _, mask_valid = guarded(mask)
    query('clock.unknown_bits', [mask], f'(({mask_valid} >= 512) and ({raw} < 9007199254740992))', 'bitmask', 'mapping_review')
    case('clock.unknown_bits', 'known', {mask: '511+0x10'})
    case('clock.unknown_bits', 'unknown', {mask: '512+0x10'}, 512)

    counters = [
        ('thermal.slowdown_seconds', 'DCGM_FI_DEV_THERMAL_VIOLATION', 1000000000, 'seconds'),
        ('pcie.replay_increase', 'DCGM_FI_DEV_PCIE_REPLAY_COUNTER', 1, 'events'),
        ('nvlink.crc_increase', 'DCGM_FI_DEV_NVLINK_CRC_ERROR_TOTAL', 1, 'errors'),
        ('nvlink.recovery_increase', 'DCGM_FI_DEV_NVLINK_RECOVERY_TOTAL', 1, 'events'),
        ('nvlink.replay_increase', 'DCGM_FI_DEV_NVLINK_REPLAY_TOTAL', 1, 'events')]
    for query_id, field, divisor, unit in counters:
        query(query_id, [field], f'({counter_query(field, True)} / {divisor})', unit, 'recent_activity_dashboard')
        for name, values, expected in [
            ('unchanged_history', '7+0x10', 0), ('increment', f'0+{divisor}x10', 10),
            ('reset', '7 7 7 7 7 0 0 0 0 0 0', 0),
            ('nan_in_window', '0 1 NaN 1 1 1 1 1 1 1 1', None),
            ('negative', '-1+0x10', None), ('missing', None, None),
            ('old', '7 _ _ _ _ _ _ _ _ _ _', None),
            ('sentinel', '9223372036854775792+0x10', None)]:
            case(query_id, name, {field: values}, expected)
    catalog = {'schema_version': '0.1.0', 'scope': 'synthetic_review_only',
               'production_admitted': False, 'queries': queries}
    fixture = {'rule_files': [], 'evaluation_interval': '30s', 'tests': cases}
    return {'catalog/thermal-links-review-queries.yaml': catalog,
            'catalog/thermal-links-review-queries.json': catalog,
            'tests/thermal-links-review.promtool.yaml': fixture}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, data in build().items():
        text = (json.dumps(data, ensure_ascii=False, indent=2) + '\n' if name.endswith('.json')
                else yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120))
        path = ROOT / name
        if args.check:
            if path.read_text() != text:
                raise SystemExit(f'生成文件需更新: {path}')
        else:
            path.write_text(text)
    print('PASS: 行重映射、温度、时钟和互联查询与样本一致')


if __name__ == '__main__':
    main()
