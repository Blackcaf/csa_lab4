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

    def handle_arithmetic(self, opcode: Opcode):
        """
        Форт берет два числа с вершины стека.
        В RISC это:
        1. Считываем верхний элемент стека (TOS) в R2, смещаем указатель стека (R4)
        2. Считываем следующий элемент в R1, смещаем указатель (R4)
        3. Выполняем операцию: R1 = R1 op R2
        4. Кладем результат обратно на стек
        """
        # Указатель стека данных у нас в R4. Стек растет вниз.
        self.emit(Opcode.LD, 2, 4, 0, f"pop R2 (arg2)")
        self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")

        self.emit(Opcode.LD, 1, 4, 0, f"pop R1 (arg1)")
        self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")

        self.emit(opcode, 1, 1, 2, f"R1 = R1 {opcode.name} R2")

        self.emit(Opcode.SUB, 4, 4, 1, "SP -= 1")
        self.emit(Opcode.ST, 1, 4, 0, f"push R1 (result)")

    def handle_number(self, num: int):
        """Помещает константу на вершину стека"""
        addr = self.emit(Opcode.LDI, 1, 0, 0, f"LDI R1, {num}")
        self.instructions.append(struct.pack(">i", num))

        self.debug_log.append(f"0x{addr+1:04X} | [LDI IMM] {num}")

        self.emit(Opcode.SUB, 4, 4, 1, "SP -= 1")
        self.emit(Opcode.ST, 1, 4, 0, "push R1 (num)")

    def handle_memory(self, opcode: Opcode):
        """
        Операции с памятью.
        @ (fetch) берет адрес с вершины стека, читает значение по этому адресу и кладет обратно на стек.
        ! (store) берет адрес с вершины стека, затем значение, и пишет значение по адресу.
        """
        if opcode == Opcode.LD:
            self.emit(Opcode.LD, 2, 4, 0, "pop addr to R2")
            self.emit(Opcode.LD, 1, 2, 0, "R1 = MEM[R2]")
            self.emit(Opcode.ST, 1, 4, 0, "push R1")

        elif opcode == Opcode.ST:
            self.emit(Opcode.LD, 2, 4, 0, "pop addr to R2")
            self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")
            self.emit(Opcode.LD, 1, 4, 0, "pop val to R1")
            self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")
            self.emit(Opcode.ST, 1, 2, 0, "MEM[R2] = R1")

    def handle_io(self, opcode: Opcode):
        """Ввод-вывод через порты (port-mapped I/O)"""
        if opcode == Opcode.IN:
            self.emit(Opcode.IN, 1, 0, 0, "IN R1, Port 0")
            self.emit(Opcode.SUB, 4, 4, 1, "SP -= 1")
            self.emit(Opcode.ST, 1, 4, 0, "push R1 (IN)")
        elif opcode == Opcode.OUT:
            self.emit(Opcode.LD, 1, 4, 0, "pop R1 to OUT")
            self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")
            self.emit(Opcode.OUT, 1, 1, 0, "OUT R1, Port 1")

    def translate(self, text: str):
        tokens = self.parse_tokens(text)

        # Начальная инициализация: установим SP (R4) на дно памяти (например, адрес 2047)
        # Установим R5 (стек возврата/циклов) на адрес 4047
        self.emit(Opcode.LDI, 4, 0, 0, "Init Data Stack Ptr")
        self.instructions.append(struct.pack(">i", 2047))
        self.debug_log.append(f"      | [IMM] 2047")

        for token in tokens:
            token_lower = token.lower()

            if token_lower in BUILTIN_WORDS:
                op = BUILTIN_WORDS[token_lower]
                if op in [Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD, Opcode.CMP]:
                    self.handle_arithmetic(op)
                elif op in [Opcode.LD, Opcode.ST]:
                    self.handle_memory(op)
                elif op in [Opcode.IN, Opcode.OUT]:
                    self.handle_io(op)

            elif token_lower == "if":
                self.emit(Opcode.LD, 1, 4, 0, "pop condition to R1")
                self.emit(Opcode.ADD, 4, 4, 1, "SP += 1")
                addr = self.emit(Opcode.JMP, 0, 1, 0, "JMP IF ZERO (stub)")
                self.jump_stack.append(('if', addr))

            elif token_lower == "else":
                addr = self.emit(Opcode.JMP, 0, 0, 0, "JMP to end (stub)")
                orig_type, orig_addr = self.jump_stack.pop()
                if orig_type != 'if':
                    raise ValueError("Unmatched 'else'")

                target = len(self.instructions)
                self.instructions[orig_addr] = struct.pack(">Biii", Opcode.JMP.value, target, 1, 0)

                self.jump_stack.append(('else', addr))

            elif token_lower == "then":
                orig_type, orig_addr = self.jump_stack.pop()
                target = len(self.instructions)
                if orig_type == 'if':
                    self.instructions[orig_addr] = struct.pack(">Biii", Opcode.JMP.value, target, 1, 0)
                elif orig_type == 'else':
                    self.instructions[orig_addr] = struct.pack(">Biii", Opcode.JMP.value, target, 0, 0)
                else:
                    raise ValueError("Unmatched 'then'")

            else:
                try:
                    num = int(token)
                    self.handle_number(num)
                except ValueError:
                    print(f"Unknown token: {token}")

        self.emit(Opcode.HLT, 0, 0, 0, "HALT")

def main():
    if len(sys.argv) < 3:
        print("Usage: python translator.py <input.f> <output.bin>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, "r", encoding="utf-8") as f:
        source_code = f.read()

    translator = Translator()
    translator.translate(source_code)

    write_binary(output_file, translator.instructions, translator.debug_log)
    print(f"Compiled {len(translator.instructions)} machine words to {output_file}")

if __name__ == "__main__":
    main()
