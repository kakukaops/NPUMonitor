"""Run inside the simulator container via scripts/lab.sh."""
import argparse
import json
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['scenario', 'state', 'events', 'notify-test'])
parser.add_argument('name', nargs='?')
args = parser.parse_args()
if args.action == 'scenario' and not args.name:
    parser.error('scenario requires a name')
paths = {'scenario': 'http://gpu-simulator:9400/scenario',
         'state': 'http://gpu-simulator:9400/state',
         'events': 'http://notification-receiver:9080/events',
         'notify-test': 'http://notification-receiver:9080/webhook'}
data = None
if args.action == 'scenario':
    data = json.dumps({'name': args.name}).encode()
elif args.action == 'notify-test':
    data = json.dumps({'source': 'manual-smoke-test', 'simulated': True,
                       'message': 'Receiver reachability only; not a Nightingale alert.'}).encode()
request = urllib.request.Request(paths[args.action], data=data,
                                 headers={'Content-Type': 'application/json'})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request, timeout=10) as response:
    print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
