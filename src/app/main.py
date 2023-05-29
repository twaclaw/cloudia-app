import asyncio
import asyncio_mqtt as aiomqtt
import argparse
import yaml
from pathlib import Path
import os
import logging
import ujson

from .decoder import Decoder


logger = logging.getLogger('cloudia-main')


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
                    # deveui = payload['end_device_ids']['dev_eui']
                    uplink = payload['uplink_message']
                    f_port, frm_payload = uplink['f_port'], uplink['frm_payload']
                except Exception:
                    logger.exception("Invalid uplink received")

                dec = Decoder(f_port, frm_payload)
                dec.read_epochs()

if __name__ == '__main__':
    asyncio.run(main())
