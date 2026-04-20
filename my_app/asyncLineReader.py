import httpx
from typing import Optional, Union, List

class AsyncLineReader:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.buffer = ""
        self.done = False

    async def __aiter__(self):
        async for chunk in self.response.aiter_text():
            self.buffer += chunk

            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                yield line

        self.done = True

        if self.buffer:
            yield self.buffer
            self.buffer = ""
    
    async def next_line(self) -> Union[Optional[str], str]:
        while True:

            # 1. Check if we have a complete line in the buffer
            pos = self.buffer.find("\n")
            if pos != -1:
                line = self.buffer[:pos].rstrip("\r")
                self.buffer = self.buffer[pos + 1:]
                return line  # Ok(Some(line))

            # 2. If stream is done
            if self.done:
                if self.buffer == "":
                    return None  # Ok(None)

                line = self.buffer
                self.buffer = ""
                return line.rstrip("\r")  # Ok(Some(line))

            # 3. Fetch next chunk
            try:
                chunk = await self.response.aread()

                if not chunk:
                    self.done = True
                    continue

                text = chunk.decode("utf-8", errors="ignore")
                self.buffer += text

            except Exception as e:
                return f"Failed to read response chunk: {e}"  # Err(...)

    async def peek_line(self) -> Union[Optional[str], str]:
        # ensure the buffer has at least one full line or stream is done
        if "\n" not in self.buffer and not self.done:
            while True:
                try:
                    chunk = await self.response.aread()

                    if not chunk:
                        self.done = True
                        break

                    text = chunk.decode("utf-8", errors="ignore")
                    self.buffer += text

                    if "\n" in self.buffer:
                        break

                except Exception as e:
                    raise RuntimeError(f"Failed to read response chunk: {e}")

        # 2. If buffer is empty → nothing to peek
        if not self.buffer:
            return None

        # 3. Return first line WITHOUT consuming it
        pos = self.buffer.find("\n")

        if pos != -1:
            return self.buffer[:pos]  # Rust: &self.buffer[..pos]

        # 4. No newline but buffer has data → return full buffer
        return self.buffer

    async def read_csv_row(self) -> Optional[List[str]]:

        # 1. Read first line
        first_line = await self.next_line()

        if first_line is None:
            return None

        fields: List[str] = []
        current: str = ""
        in_quotes: bool = False

        # 2. Parse first line
        current, in_quotes = parse_csv_line_partial(
            first_line,
            fields,
            current,
            in_quotes
        )

        # 3. If still inside quotes → continue across lines
        while in_quotes:
            current += "\n"

            next_line = await self.next_line()

            if next_line is None:
                break

            current, in_quotes = parse_csv_line_partial(
                next_line,
                fields,
                current,
                in_quotes
            )

        # 4. Finalize last field
        fields.append(current)

        return fields