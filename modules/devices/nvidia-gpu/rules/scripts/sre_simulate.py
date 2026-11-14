#!/usr/bin/env python3
"""Control only the current local synthetic GPU source; do not change real devices."""
import argparse,json
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[5]
def main():
    p=argparse.ArgumentParser();p.add_argument('scenario',nargs='?',default='list');p.add_argument('--metric',help='Master metric_id; apply only to selected GPU/switch');p.add_argument('--value',type=float);p.add_argument('--rate',type=float,help='Counter increment per second');p.add_argument('--identity',default='GPU-CONTRACT-0000');args=p.parse_args()
    token=(ROOT/'.local/gpu-os-sre-master/admin-token').read_text().strip();headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    path='/scenarios' if args.scenario=='list' else '/coverage' if args.scenario=='coverage' else '/events' if args.scenario=='events' else '/control'
    payload={'scenario':args.scenario}
    if args.metric:
        master=json.loads((ROOT/'modules/devices/nvidia-gpu/rules/runtime/src/npumonitor_rules/master-profile.json').read_text())
        if args.metric not in master['metric_ids']:p.error('Metric has no supported numeric simulation')
        if (args.value is None)==(args.rate is None):p.error('Choose exactly one of --value or --rate')
        name=master['metric_ids'][args.metric]
        identity={'switch_id' if args.identity.startswith('SW-') else 'UUID':args.identity}
        if args.rate is not None:
            if master['metric_contracts'][name]['kind']!='counter' or args.rate<0:p.error('--rate requires a counter and a nonnegative rate')
            payload['counter_activity']=[{'metric':name,'identity':identity,'rate_per_second':args.rate}]
        else:payload['overrides']=[{'metric':name,'identity':identity,'value':args.value}]
        path='/control'
    body=None if path!='/control' else json.dumps(payload).encode()
    with urlopen(Request('http://127.0.0.1:19477'+path,data=body,headers=headers),timeout=10) as response:value=json.load(response)
    print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
