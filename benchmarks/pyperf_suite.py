"""Calibrated subprocess pyperf Runner suite against the installed distribution."""

import pyperf
from run import workloads


def command_line(command, args):
    command.extend(["--engine", args.engine, "--workload", args.workload])


runner = pyperf.Runner(add_cmdline_args=command_line)
runner.argparser.add_argument("--engine", choices=["python", "rust"], default="python")
runner.argparser.add_argument(
    "--workload", default="", help="Optional workload name substring"
)
args = runner.parse_args()
runner.metadata["engine"] = args.engine
runner.metadata["seed"] = 1729
for name, function, _loops, _counters, _new_only in workloads(args.engine, False):
    if "fake_telegram" not in name and args.workload in name:
        runner.bench_func(name, function)
