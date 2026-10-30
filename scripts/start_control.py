"""Two listeners, one controller process/state/lock. Only broker is sandbox reachable."""
import asyncio
import contextlib
from pathlib import Path
import signal
import sys
import uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.control import app
from lab.broker_app import create_app


async def main():
    public = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8080, access_log=False))
    broker = uvicorn.Server(uvicorn.Config(create_app(), host="0.0.0.0", port=8082, access_log=False))
    public.capture_signals = contextlib.nullcontext
    broker.capture_signals = contextlib.nullcontext
    loop = asyncio.get_running_loop()
    def stop():
        public.should_exit = True
        broker.should_exit = True
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)
    await asyncio.gather(public.serve(), broker.serve())


if __name__ == "__main__":
    asyncio.run(main())
