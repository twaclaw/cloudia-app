import asyncio
import asyncio_mqtt as aiomqtt
import argparse
import yaml
from pathlib import Path
import os
import logging
from dataclasses import dataclass
from enum import Enum
from base64 import b64encode
import re
import ujson


class TimeUnit(Enum):
    s = 's'
    m = 'm'
    h = 'h'


logger = logging.getLogger('cloudia-downlink')


def get_time_reg(value: int, unit: TimeUnit) -> int:
    if unit == TimeUnit.s:
        return (1 << 7) | (value & 0x7F)
    elif unit == TimeUnit.m:
        return (1 << 6) | (value & 0x3F)
    else:
        return value & 0x3F


@dataclass
class Configuration():
    period: int
    nsamples: int
    R1: int = 0x00
    R2: int = 0x00

    def payload(self):
        conf = bytearray([self.R1, self.R2, self.period, self.nsamples])
        return b64encode(conf).decode('ascii')


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=str, help="Configuration file")
    parser.add_argument("deviceId", type=str, help="Device id")
    parser.add_argument("--period", type=str,
                        help="Period r'^[0-9]+[smh]$", default="10s")
    parser.add_argument("--nsamples", type=int,
                        help="Number of samples", default=10)

    try:
        args = parser.parse_args()
    except Exception as ex:
        logger.error("Argument parsing failed!")
        raise ex

    reg = r"(?P<value>[0-9]+)(?P<units>[smh])"
    rmatch = re.match(reg, args.period)
    if not rmatch:
        raise ValueError(f"Invalid option --period {args.period}")

    if args.nsamples and args.nsamples > 255:
        raise ValueError("nsamples must be at most 255")

    try:
        config = yaml.safe_load(
            Path(os.path.realpath(args.config)).read_text())
    except Exception as ex:
        logging.error("Invalid configuration file!")
        raise ex

    lns_config = config['lns']
    topics = f"v3/{lns_config['appid']}/devices/{args.deviceId}/down/push"

    v_d = rmatch.groupdict()
    units, value = TimeUnit(v_d['units']), int(v_d['value'])
    downlink = {
        "downlinks": [{
            "f_port": 144,
            "frm_payload": Configuration(period=get_time_reg(value, units),
                                         nsamples=args.nsamples).payload(),
            "priority": "NORMAL"
        }]
    }

    async with aiomqtt.Client(
            hostname=lns_config['host'],
            port=lns_config['port'],
            username=lns_config['appid'],
            password=lns_config['appkey']
    ) as client:
        await client.publish(topics, payload=ujson.dumps(downlink))

if __name__ == '__main__':
    asyncio.run(main())
