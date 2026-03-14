import re
import subprocess

from .base import LogDriver, LogResult


class JournalctlLogDriver(LogDriver):
    """journalctl --user -u <service> -n <lines> --no-pager [--since <since>]"""

    def tail(self, lines: int = 100, since: str = None) -> LogResult:
        spec = self.manifest.get("spec", {})
        logs_spec = spec.get("logs", {})
        service_name = logs_spec.get("service_name", "")
        configured_lines = logs_spec.get("lines", 100)
        actual_lines = lines or configured_lines
        filter_rules = logs_spec.get("filter_rules", [])

        cmd = ["journalctl", "--user", "-u", service_name, f"-n{actual_lines}", "--no-pager"]
        if since:
            cmd += ["--since", since]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            raw_lines = result.stdout.splitlines()
        except Exception:
            return LogResult(lines=[], source=f"journalctl:{service_name}", total_lines=0)

        # 应用过滤规则
        filtered = self._apply_filter_rules(raw_lines, filter_rules)

        return LogResult(lines=filtered, source=f"journalctl:{service_name}", total_lines=len(raw_lines))

    def _apply_filter_rules(self, lines: list, filter_rules: list) -> list:
        if not filter_rules:
            return lines

        include_patterns = [re.compile(r["pattern"]) for r in filter_rules if r.get("action") == "include"]
        exclude_patterns = [re.compile(r["pattern"]) for r in filter_rules if r.get("action") == "exclude"]

        result = []
        for line in lines:
            # include 规则：任一匹配则保留（无 include 规则则默认保留所有）
            if include_patterns:
                if not any(p.search(line) for p in include_patterns):
                    continue
            # exclude 规则：任一匹配则丢弃
            if any(p.search(line) for p in exclude_patterns):
                continue
            result.append(line)

        return result
