import asyncio
import argparse
import yaml
from pathlib import Path
import os
import logging


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
    print(lns_config)

    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # context.load_verify_locations('./tc.trust')
    # topics = (f"v3/{lns_config['appid']}/devices/+/up",)
    # ttn_client = TTNClient(lns_config, None)


if __name__ == '__main__':
    asyncio.run(main())
