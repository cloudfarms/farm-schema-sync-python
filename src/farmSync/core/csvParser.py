from farmSync.models import SyncItem, SectionItem, PythonTableInfo
from typing import Optional, Union, cast
from farmSync.core.enums import State, CsvOperation
from farmSync.core.transforms import Transforms
from farmSync.core.pipelineChannel import PipelineChannel
import csv


class CsvParser:

    def __init__(self, channel: PipelineChannel) -> None:
        self.buffer = None
        self.channel = channel
        self.state = State.START
        self.translation = None
        self.cols = []

    def translateToPython(self, line: Union[SectionItem, SyncItem],
                          tableMap: dict[str, PythonTableInfo])-> Union[SectionItem, SyncItem]:
        if line["type"] == State.SECTION_NAME:
            line = cast(SectionItem, line)
            self.translation = tableMap[line["table"]]
        if line["type"] == State.HEADER:
            line = cast(SyncItem, line)
            self.cols = line["data"]
        if line["type"] == State.ROWS:
            line = cast(SyncItem, line)
            cols = []
            if self.translation is None:
                raise Exception("Translation is not set for this table")
            for i, col in enumerate(line["data"]):
                translation = self.translation.columns[self.cols[i]]
                cols.append(Transforms.strToType(col, translation.typeName, self.channel.dialect))
            line["data"] = tuple(cols)
        return line
    
    def parseLine(self, line:Optional[str]) -> Optional[Union[SectionItem, SyncItem]]:
        """
        Parses lines to more easily readable stuff for consumer. If return is None, line is ignored 
        """
        if self.state == State.START:
            if line is None:
                raise Exception("Invalid CSV Response: empty body")
            if line.strip() != "data":
                raise Exception("Invalid CSV Response: expected first line to be \"data\"."
                                f" Got {line}")
            self.state = State.METADATA_HEADER
            return None

        if not line:
            return None

        line = line.strip()

        if line == "*":
            return None

        if line.endswith("_upserted") or line.endswith("_deleted"):
            self.state = State.SECTION_NAME

        if self.state == State.METADATA_HEADER:
            self.state = State.METADATA_ROW
            self.channel.updateHeader = list(csv.reader([line]))[0] 
            return None
        
        if self.state == State.METADATA_ROW:
            self.state = State.WAIT
            self.channel.updateRow = list(csv.reader([line]))[0] 
            return None

        if self.state == State.SECTION_NAME:
            operation = line.split("_")[-1]
            tableName = "_".join(line.split("_")[:-1])
            self.state = State.HEADER
            return SectionItem({"type": State.SECTION_NAME, "table": tableName ,
                                "operation": CsvOperation(operation)})

        if self.state == State.HEADER:
            self.state = State.ROWS
            return SyncItem({"type" : State.HEADER, "data": tuple(list(csv.reader([line]))[0])})
        
        if self.state == State.ROWS:
            # take into account partial lines, which can be in quotes
            parsed, isDone = Transforms.parseCsvLine(line, self.buffer is not None, self.buffer)
            if isDone:
                self.buffer = None
                return SyncItem({"type": State.ROWS, "data": tuple(parsed)})
            else:
                self.buffer = parsed
                return None
        
        return None