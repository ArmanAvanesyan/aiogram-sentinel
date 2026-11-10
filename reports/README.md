# Verification evidence

Maintain concise checked-in reports for meaningful audits. Generate Bandit,
dependency-audit and coverage JSON as ignored local output or CI artifacts.
Bandit CI retains the full inventory and gates medium/high findings; internal
assertions are not runtime input validation. Dependency audits run on Python3.11+
and must fail on known vulnerabilities, without blanket ignores.
