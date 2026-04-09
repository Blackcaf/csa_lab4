import struct
# pack(format, v1, v2, ...) - упаковывает данные в байты по заданному формату
# unpack(format, bytes) - распаковывает байты в данные по заданному формату
from enum import Enum, auto

class Register(Enum):
    R0 = 0 # всегда хранит 0
    R1 = 1 # общий
    R2 = 2 # общий
    R3 = 3 # общий
    R4 = 4 # указатель на стек
    R5 = 5 # указатель стека возврата
    R6 = 6 # FP(GP) указатель на глобальну память
    R7 = 7 # счетчик команд IP(PC)

class Opcode(Enum):
    # арифметика
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    CMP = auto() # влияет на флаги zero/negative

    # память
    LD = auto() # LD reg_dest, reg_addr
    ST = auto() # ST reg_src, reg_addr

    # работа с константами
    LDI = auto() # LDI reg_dest, imm32 (команда занимает 2 слова: [opcode, reg, 0, 0] [imm_value])

    # ввод-вывод портов
    IN = auto() # IN reg_dest, port_num
    OUT = auto() # OUT port_num, reg_src

    # переходы
    JMP = auto() # JMP reg_addr
    JZ = auto() # JZ reg_addr (прыжок если флаг zero == 1)
    JNZ = auto() # JNZ reg_addr
    CALL = auto() # CALL reg_addr
    RET = auto() # RET(возврат по адресу из вершины стека возврата)

    HLT = auto() # остановка процессора

# стркуктура инструкции: [opcode, arg1, arg2, arg3]
# 1 байт = opcode
# 1 байт = arg1 (регистр или значение)
# 1 байт = arg2 (регистр или значение)
# 1 байт = arg3 (регистр) - для RISC операций вида r3 = r1 + r2
# итого 32 бита (1 машинное слово)

INSTRUCTION_FORMAT = ">BBBB"

# кодирует одну команду в 4 байта
def encode_instruction(opcode: Opcode, arg1: int = 0, arg2: int = 0, arg3: int = 0) -> bytes:
    return struct.pack(INSTRUCTION_FORMAT, opcode.value, arg1, arg2, arg3)

# декодирует 4 байта в команду (opcode, arg1, arg2, arg3)
def decode_instruction(data: bytes) -> tuple:
    return struct.unpack(INSTRUCTION_FORMAT, data)

# сохраняет бинарник или отладочный лог
# instructions - список байтовых строк
def write_binary(filepath: str, instructions: list[bytes], debug_log: list[str] = None):
    with open(filepath, "wb") as f:
        for log_line in debug_log:
            f.write(log_line + "\n")

    # лог-файл(опция binary)
    if debug_log:
        with open(filepath + ".txt", "w", encodinf="utg-8") as f:
            for log_line in debug_log:
                f.write(log_line + "\n")

# читает бинарный файл и возвращает список корежей инструкций
def read_binary(filepath: str) -> list[tuple]:
    instructions = []
    with open(filepath, "rb") as f:
        while chunk := f.read(4):
            if len(chunk) == 4:
                instructions.append(decode_instruction(chunk))
    return instructions