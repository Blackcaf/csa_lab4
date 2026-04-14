import sys
import struct
from isa import Opcode, Register, encode_instruction, write_binary

BUILTIN_WORDS = {
    '+': Opcode.ADD,
    '-': Opcode.SUB,
    '*': Opcode.MUL,
    '/': Opcode.DIV,
    'mod': Opcode.MOD,
    '=': Opcode.CMP,
    '@': Opcode.LD,
    '!': Opcode.ST,
    'in': Opcode.IN,
    'out': Opcode.OUT
}

class Translator:
    def __init__(self):
        # Списки для хранения машинного кода и отладочного лога
        self.instructions = []
        self.debug_log = []
        # Хранение меток для переходов (if/else/loops)
        self.jump_stack = []

    def emit(self, opcode: Opcode, arg1: int = 0, arg2: int = 0, arg3: int = 0, debug_text: str = ""):
        """Добавляет одну команду в бинарник и лог"""
        # Индекс текущей инструкции (ее будущий адрес в памяти инструкций)
        addr = len(self.instructions)
        binary_code = encode_instruction(opcode, arg1, arg2, arg3)
        self.instructions.append(binary_code)

        log_entry = f"0x{addr:04X} | {opcode.name} {arg1} {arg2} {arg3} | {debug_text}"
        self.debug_log.append(log_entry)
        return addr

    def parse_tokens(self, text: str) -> list[str]:
        """Убирает комментарии и разбивает текст на слова (токены)"""
        lines = text.split('\n')
        clean_text = ""
        for line in lines:
            if '\\' in line:
                line = line.split('\\')[0]
            clean_text += line + " "

        return clean_text.split()
