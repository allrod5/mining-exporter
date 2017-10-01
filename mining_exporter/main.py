import argparse
import sys
from datetime import datetime
from time import sleep

from parse import parse
from prometheus_client import start_http_server
from systemd import journal

from mining_exporter.utils import escape_ansi

version = "0.1.0"


def main():
    args = get_args()
    listen_port = args.port
    sleep_time = args.frequency

    start_http_server(listen_port)

    ethminer_service = journal.Reader()
    ethminer_service.add_match(_SYSTEMD_UNIT='eth-miner.service')

    report = {
        'ethminer-version': '?',
    }

    t1 = datetime.now()
    while True:
        t0 = t1
        sleep(sleep_time)
        t1 = datetime.now()

        ethminer_service.seek_realtime(t0)
        entry = ethminer_service.get_next()

        solutions_found = 0
        solutions_accepted = 0
        jobs_received = 0

        while valid(entry, t0, t1):
            message = escape_ansi(entry['MESSAGE'])
            ethminer_status_message_format = (
                "  m  {}|ethminer  Speed  {} Mh/s    {}  [{}] Time: {}")
            parsed = parse(ethminer_status_message_format, message)
            if parsed:
                ts, total_hashrate, gpus_hashrate, _, running_time = parsed
                report['hashrate'] = dict(
                    [(k, float(v)) for gpu in gpus_hashrate.split("  ")
                     for k, v in gpu.split(" ")],
                    total=total_hashrate)
                report['running_time'] = running_time
                continue

            cuda_solution_found_message_format = (
                "  ℹ  {}|CUDA{}     Solution found;"
                " Submitting solution to {} ...")
            parsed = parse(cuda_solution_found_message_format, message)
            if parsed:
                solutions_found += 1
                continue

            stratum_solution_accepted_format = (
                "  ℹ  {}|stratum    B-) Submitted and accepted.")
            parsed = parse(stratum_solution_accepted_format, message)
            if parsed:
                solutions_accepted += 1
                continue

            stratum_new_job_message_format = (
                "  ℹ  {}|stratum   Received new job {}")
            parsed = parse(stratum_new_job_message_format, message)
            if parsed:
                jobs_received += 1
                continue

        report['solutions'] = solutions_found
        report['shares'] = solutions_accepted
        report['jobs'] = jobs_received


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

