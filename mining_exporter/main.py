import argparse
import sys
from datetime import datetime
from time import sleep

from parse import parse
from prometheus_client import start_http_server
from prometheus_client import Gauge
from prometheus_client import Counter
from systemd import journal

from mining_exporter.utils import escape_ansi

version = "0.1.0"

REQUEST_TOTAL_HASHRATE = Gauge('total_hashrate', 'Total Hashrate', 'total')
REQUEST_GPUS_HASHRATE = Gauge('gpus_hashrate', 'GPUs Hashrates', ['gpu'])

REQUEST_JOBS = Counter('jobs', 'Received jobs from Stratum')
REQUEST_SOLUTIONS = Counter('solutions', 'Total of solutions found')
REQUEST_SHARES = Counter('shares', 'Total of solutions accepted')


def main():
    args = get_args()
    listen_port = args.port
    sleep_time = args.frequency

    start_http_server(listen_port)

    ethminer_service = journal.Reader()
    ethminer_service.add_match(_SYSTEMD_UNIT='eth-miner.service')

    t1 = datetime.now()
    while True:
        t0 = t1
        sleep(sleep_time)
        t1 = datetime.now()

        ethminer_service.seek_realtime(t0)
        entry = ethminer_service.get_next()

        while valid(entry, t0, t1):
            message = escape_ansi(entry['MESSAGE'])
            ethminer_status_message_format = (
                "  m  {}|ethminer  Speed  {} Mh/s    {}  [{}] Time: {}")
            parsed = parse(ethminer_status_message_format, message)
            if parsed:
                ts, total_hashrate, gpus_hashrate, _, running_time = parsed
                REQUEST_TOTAL_HASHRATE.set(total_hashrate)
                gpus_hashrates = [
                    (k, float(v))
                    for gpu in gpus_hashrate.split("  ")
                    for k, v in gpu.split(" ")]
                for gpu, hashrate in gpus_hashrates:
                    REQUEST_GPUS_HASHRATE.labels(gpu).set(hashrate)
                continue

            cuda_solution_found_message_format = (
                "  ℹ  {}|CUDA{}     Solution found;"
                " Submitting solution to {} ...")
            parsed = parse(cuda_solution_found_message_format, message)
            if parsed:
                REQUEST_SOLUTIONS.inc()
                continue

            stratum_solution_accepted_format = (
                "  ℹ  {}|stratum    B-) Submitted and accepted.")
            parsed = parse(stratum_solution_accepted_format, message)
            if parsed:
                REQUEST_SHARES.inc()
                continue

            stratum_new_job_message_format = (
                "  ℹ  {}|stratum   Received new job {}")
            parsed = parse(stratum_new_job_message_format, message)
            if parsed:
                REQUEST_JOBS.inc()
                continue


def valid(entry, t0, t1):
    return (
        entry.get('__REALTIME_TIMESTAMP')
        and t0 < entry['__REALTIME_TIMESTAMP'] <= t1)


def get_args():
    parser = argparse.ArgumentParser(
        description="Prometheus mining metrics exporter v" + str(version))
    parser.add_argument(
        "-f", "--frequency", metavar="<seconds>", required=False,
        help="Interval in seconds between checking measures", default=1,
        type=int)
    parser.add_argument(
        "-p", "--port", metavar="<port>", required=False,
        help="Port for listening", default=8601, type=int)
    args = parser.parse_args()

    return args

if __name__ == "__main__":
    sys.exit(main())

