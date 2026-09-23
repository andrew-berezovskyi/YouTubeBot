"""Run only from source with Python, not an old packaged EXE."""
import argparse
from discovery.service import run

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Discover, download and screen videos. Default: no uploads.')
    parser.add_argument('--watch',action='store_true',help='Repeat at the configured interval')
    parser.add_argument('--process',action='store_true',help='Pass accepted videos through original pipeline; private uploads')
    parser.add_argument('--publish',action='store_true',help='Explicitly enable public uploads (requires --process)')
    args=parser.parse_args()
    if args.publish and not args.process: parser.error('--publish requires --process')
    try: run(args.watch,args.process,args.publish)
    except KeyboardInterrupt: print('Stopped. State saved; interrupted uploads require review.')
