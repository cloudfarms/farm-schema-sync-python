
class SqlGenerator:

    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _getPrimaryKeyString(self, keys: list[str]) -> str:
        if not keys:
            return ""
        quotedKeys = [self._quoteIdent(key) for key in keys]
        return f"PRIMARY KEY ({','.join(quotedKeys)})"