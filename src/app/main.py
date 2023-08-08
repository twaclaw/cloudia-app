import asyncio
import aiomqtt
import argparse
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client import Point
import logging
import os
from pathlib import Path
import ujson
from sys import stdout
from typing import List
import yaml

from .decoder import decode, VarName


logger = logging.getLogger('cloudia-main')
consoleHandler = logging.StreamHandler(stdout)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=str, help="Configuration file")

    try:
        args = parser.parse_args()
    except Exception as ex:
        logger.error("Argument parsing failed!")
        raise ex

    try:
        config = yaml.safe_load(
            Path(os.path.realpath(args.config)).read_text())
    except Exception as ex:
        logging.error("Invalid configuration file!")
        raise ex

    lns_config = config['lns']
    topics = f"v3/{lns_config['appid']}/devices/+/up"

    db_cfg = config['influxdb']
    bucket, org = db_cfg['bucket'], db_cfg['org']

    logger.debug("Starting main loop ...")

    async with aiomqtt.Client(
            hostname=lns_config['host'],
            port=lns_config['port'],
            username=lns_config['appid'],
            password=lns_config['appkey']
    ) as client:
        async with client.messages() as messages:
            await client.subscribe(topics)
            async for message in messages:
                try:
                    payload = ujson.loads(message.payload.decode())
                    deveui = payload['end_device_ids']['dev_eui']
                    uplink = payload['uplink_message']
                    logger.debug(f"Received uplink: {uplink}")
                    f_port, frm_payload = uplink['f_port'], uplink['frm_payload']
                    dec = decode(f_port, frm_payload)
                    points: List[Point] = []
                    for t, v in dec:
                        T, H = v[VarName.T], v[VarName.H]
                        logger.debug(f"t: {t}, values: ({T}, {H})")
                        points.append(Point("TH")
                                      .tag("deveui", deveui)
                                      .field("T", T)
                                      .field("H", H)
                                      .time(t))

                    async with InfluxDBClientAsync(url=db_cfg['url'],
                                                   token=db_cfg['token'],
                                                   timeout=db_cfg['timeout'],
                                                   verify_ssl=db_cfg['verify_ssl']) as client:
                        write_api = client.write_api()
                        await write_api.write(bucket, org, points)
                except Exception:
                    logger.exception(f"Invalid uplink received {uplink}")

if __name__ == '__main__':
    asyncio.run(main())
