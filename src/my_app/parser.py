from my_app.models import *
from typing import Optional, Union, cast
from my_app.enums import State, CsvOperation
from my_app.transforms import Transforms
import csv
from my_app.pipelineChannel import PipelineChannel


class Parser:

    def __init__(self, channel: PipelineChannel) -> None:
        self.buffer = None
        self.channel = channel
        self.state = State.START
        self.translation = None

    def translateToPython(self, line: Union[SectionItem, SyncItem], tableMap: dict[str, PythonTableInfo]):
        if line["type"] == State.SECTION_NAME:
            # find the table map for this table and save it to context for later usage
            line = cast(SectionItem, line)
            self.translation = tableMap[line["table"]]
        if line["type"] == State.ROWS:
            # use the saved table map to properly translate the data
            line = cast(SyncItem, line)
            cols = []
            if self.translation is None:
                raise Exception("Translation is not set for this table")
            for i, col in enumerate(line["data"]):
                cols.append(Transforms.strToType(col, self.translation.columns[i].typeName, self.channel.dialect))
            line["data"] = cols
        return line
    
    def parseLine(self, line:Optional[str]) -> Optional[Union[SectionItem, SyncItem]]:
        """
        Parses lines to more easily readable stuff for consumer. If return is None, line is ignored 
        """
        if self.state == State.START:
            if line is None:
                raise Exception("Invalid CSV Response: empty body")
            if line.strip() != "data":
                raise Exception(f"Invalid CSV Response: expected first line to be \"data\", got {line}")
            self.state = State.METADATA_HEADER
            return None

        if not line:
            return None

        line = line.strip()

        if line == "*":
            return None

        if len(line.split(",")) == 1 and len(line.split("_")) > 1:
            self.state = State.SECTION_NAME

        if self.state == State.METADATA_HEADER:
            self.state = State.METADATA_ROW
            self.channel.updateHeader = list(csv.reader([line]))[0] # save update data for later
            return None
        
        if self.state == State.METADATA_ROW:
            self.state = State.WAIT
            self.channel.updateRow = list(csv.reader([line]))[0] # save update data for later
            return None

        if self.state == State.SECTION_NAME:
            operation = line.split("_")[-1]
            tableName = "_".join(line.split("_")[:-1])
            self.state = State.HEADER
            return SectionItem({"type": State.SECTION_NAME, "table": tableName , "operation": CsvOperation(operation)})

        if self.state == State.HEADER:
            self.state = State.ROWS
            return SyncItem({"type" : State.HEADER, "data": list(csv.reader([line]))[0]})
        
        if self.state == State.ROWS:
            # take into account partial lines, which can be in quotes
            parsed, isDone = Transforms.parseCsvLine(line, self.buffer is not None, self.buffer)
            if isDone:
                self.buffer = None
                return SyncItem({"type": State.ROWS, "data": parsed})
            else:
                self.buffer = parsed
                return None
        
        return None