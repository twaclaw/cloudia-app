from base64 import b64decode
from enum import Enum
from typing import List, Mapping
import datetime
from pydantic import BaseModel, Field


class VarRes(Enum):
    T = 10
    H = 7


class Ports(Enum):
    SINGLE_MEAS = 80
    MULT_MEAS_OFFSET_0 = 81
    MULT_MEAS = 82
    MULT_MEAS_OFFSET_0_DIFFS = 90
    MULT_MEAS_DIFFS = 91


class Vars(BaseModel):
    T: float = Field(le=100.0, ge=-100.0)
    H: int = Field(le=100, ge=0)


class Epoch(BaseModel):
    t: datetime.datetime
    vars: Vars


class Buffer():
    def __init__(self, buf: bytearray):
        self.buf: bytearray = buf
        self.size = len(self.buf)
        self.byte_ptr = 0
        self.bit_ptr = 0
        self.MASK: bytearray = bytearray(
            [0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF])

    def read(self, nbits: int, signed: bool = False):
        sign = 0
        if signed:
            sign = (self.buf[self.byte_ptr] >> self.bit_ptr) & 0x1
            if self.bit_ptr < 7:
                self.bit_ptr += 1
            else:
                self.bit_ptr = 0
                self.byte_ptr += 1
        res = 0
        shift_by = 0
        while nbits:
            x = self.buf[self.byte_ptr]
            x >>= self.bit_ptr
            masked_bits = min(8 - self.bit_ptr, nbits)
            res |= (x & self.MASK[masked_bits - 1]) << shift_by
            shift_by += masked_bits
            nbits -= masked_bits
            if (8 - self.bit_ptr) > masked_bits:
                self.bit_ptr += masked_bits
            else:
                self.bit_ptr = 0
                self.byte_ptr += 1
        return -res if sign else res


class Decoder():
    offset: int = 0
    period: datetime.timedelta | None = None
    buffer: Buffer | None = None
    base_values: Mapping[VarRes, int] = {i: i.value for i in VarRes}
    next_values: Mapping[VarRes, int] | None = None
    status: bytearray = bytearray([0, 0, 0])

    def __init__(self, port: int, payload_base64: str):
        self.payload = b64decode(payload_base64)
        self.port = Ports(port)
        print(self.port)
        self.now = datetime.datetime.now()

        self.status[0] = self.payload[0]
        if self.port == Ports.SINGLE_MEAS:
            data = self.payload[1:]
            self.buffer = Buffer(data)
        elif self.port == Ports.MULT_MEAS_OFFSET_0:
            self.status[1] = self.payload[1]
            data = self.payload[2:]
            self.buffer = Buffer(data)
            self.next_values = {i: i.value for i in VarRes}
        elif self.port == Ports.MULT_MEAS:
            self.status[1] = self.payload[1]
            self.offset = self.payload(2)
            data = self.payload[3:]
            self.buffer = Buffer(data)
            self.next_values = {i: i.value for i in VarRes}
        elif self.port == Ports.MULT_MEAS_OFFSET_0_DIFFS:
            self.status[1] = self.payload[1]
            self.status[2] = self.payload[2]
            # number of bits used to encode the differences
            self.next_values = {VarRes.T: (self.status[2] >> 4) & 0xFF,
                                VarRes.H: self.status[2] & 0x0F}

            data = self.payload[3:]
            self.buffer = Buffer(data)
        elif self.port == Ports.MULT_MEAS_DIFFS:
            self.status[1] = self.payload[1]
            self.status[2] = self.payload[2]
            # number of bits used to encode the differences
            self.next_values = {VarRes.T: (self.status[2] >> 4) & 0xFF,
                                VarRes.H: self.status[2] & 0xFF}
            self.offset = self.payload[3]
            data = self.payload[4:]
            self.buffer = Buffer(data)

        if self.status[2] & (1 << 7):  # value in secs
            self.period = datetime.timedelta(seconds=self.status[2] & 0x7F)
        elif self.status[2] & (1 << 6):  # value in mins
            self.period = datetime.timedelta(minutes=self.status[2] & 0x3F)
        else:
            self.period = datetime.timedelta(hours=self.status[2] & 0x3F)

    def read_epochs(self) -> List[Epoch]:
        res: List[Epoch] = []

        # read the first epoch
        # TODO: get sign dynamically
        T = self.buffer.read(self.base_values[VarRes.T], signed=True)
        H = self.buffer.read(self.base_values[VarRes.H], signed=False)
        v = Vars(**{'T': (T/10.0), 'H': H})
        res.append(Epoch(**{'t': self.now, 'vars': v}))

        print(res)
