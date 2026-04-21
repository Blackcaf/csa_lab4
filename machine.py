import logging
import sys
from struct import unpack
from isa import Opcode, Register, decode_instruction, read_binary
from microcode import MicroOp, get_microcode_rom

class Cache:
    """
    Кэш данных (прямого отображения - Direct Mapped Cache).
    Простейшая реализация: кэшируем линии по одному машинному слову.
    Попадание (hit) - 1 такт, промах (miss) - несколько тактов простоя (stall).
    """
    def __init__(self, memory_size, cache_size=16):
        self.memory = [0] * memory_size
        self.cache_size = cache_size
        self.lines = [{"valid": False, "tag": -1, "data": 0} for _ in range(cache_size)]
        self.hits = 0
        self.misses = 0

    def read(self, addr) -> tuple[int, int]:
        """ Возвращает (значение, penalty_ticks) """
        idx = addr % self.cache_size
        tag = addr // self.cache_size
        line = self.lines[idx]

        if line["valid"] and line["tag"] == tag:
            self.hits += 1
            return line["data"], 0

        self.misses += 1
        line["valid"] = True
        line["tag"] = tag
        line["data"] = self.memory[addr]
        return line["data"], 5

    def write(self, addr, value) -> tuple[int, int]:
        """ Возвращает penalty_ticks. Сквозная запись (Write-Through) """
        idx = addr % self.cache_size
        tag = addr // self.cache_size
        line = self.lines[idx]

        hit = line["valid"] and line["tag"] == tag
        if hit:
            self.hits += 1
        else:
            self.misses += 1
            line["valid"] = True
            line["tag"] = tag

        line["data"] = value
        self.memory[addr] = value

        return 0 if hit else 5


class DataPath:
    """Тракт данных (Registers, ALU, Cache)"""
    def __init__(self, data_memory_size, input_buffer: list):
        self.registers = [0] * 8
        self.cache = Cache(data_memory_size)

        self.input_buffer = input_buffer
        self.output_buffer = []

        self.alu_a = 0
        self.alu_b = 0
        self.alu_out = 0

        self.zero_flag = False
        self.neg_flag = False

        self.data_memory_out = 0

    def execute_alu(self, op: MicroOp):
        if op == MicroOp.ALU_ADD:
            self.alu_out = self.alu_a + self.alu_b
        elif op == MicroOp.ALU_SUB:
            self.alu_out = self.alu_a - self.alu_b
        elif op == MicroOp.ALU_MUL:
            self.alu_out = self.alu_a * self.alu_b
        elif op == MicroOp.ALU_DIV:
            self.alu_out = self.alu_a // self.alu_b if self.alu_b != 0 else 0
        elif op == MicroOp.ALU_MOD:
            self.alu_out = self.alu_a % self.alu_b if self.alu_b != 0 else 0
        elif op == MicroOp.ALU_PASS_A:
            self.alu_out = self.alu_a
        elif op == MicroOp.ALU_PASS_B:
            self.alu_out = self.alu_b
        elif op == MicroOp.ALU_CMP:
            res = self.alu_a - self.alu_b
            self.zero_flag = (res == 0)
            self.neg_flag = (res < 0)

    def read_port(self, port_num: int) -> int:
        if port_num == 0:
            if not self.input_buffer:
                raise EOFError("Input buffer is empty")
            val = self.input_buffer.pop(0)
            if isinstance(val, str):
                return ord(val)
            return val
        return 0

    def write_port(self, port_num: int, value: int):
        if port_num == 1:
            try:
                char = chr(value)
                self.output_buffer.append(char)
                logging.debug(f"OUTPUT: '{char}'")
            except ValueError:
                self.output_buffer.append(str(value))


class ControlUnit:
    """Устройство управления (Microcoded)"""
    def __init__(self, datapath: DataPath, instruction_memory: list):
        self.dp = datapath
        self.instr_mem = instruction_memory

        self.pc = 0
        self.ir_opcode = Opcode.HLT
        self.ir_arg1 = 0
        self.ir_arg2 = 0
        self.ir_arg3 = 0
        self.ir_imm = 0

        self.tick_count = 0
        self.rom = get_microcode_rom()

    def tick(self):
        self.tick_count += 1

    def decode_and_execute(self):
        """Основной цикл (Tick-based)"""
        while True:
            instruction_bytes = self.instr_mem[self.pc] if self.pc < len(self.instr_mem) else b'\x00'*4
            if isinstance(instruction_bytes, int):
                pass

            op_val, a1, a2, a3 = decode_instruction(instruction_bytes)
            self.ir_opcode = Opcode(op_val)
            self.ir_arg1 = a1
            self.ir_arg2 = a2
            self.ir_arg3 = a3

            micro_program = self.rom.get(self.ir_opcode, self.rom[Opcode.HLT])

            for uop in micro_program:
                self.tick()
                stall_ticks = self.execute_microop(uop)

                # Добавляем штрафные такты за промахи кэша (stall)
                for _ in range(stall_ticks):
                    self.tick()

                if uop == MicroOp.FINISH_INSTRUCTION:
                    break
                elif uop == MicroOp.HALT_PROCESSOR:
                    raise StopIteration()

    def execute_microop(self, uop: MicroOp) -> int:
        """Исполняет одну микроинструкцию. Возвращает кол-во stall-тактов."""
        stall = 0
        dp = self.dp

        if uop == MicroOp.LATCH_PC_INC:
            self.pc += 1
        elif uop == MicroOp.LATCH_PC_ALU:
            self.pc = dp.alu_out

        elif uop == MicroOp.LATCH_IR:
            pass

        elif uop == MicroOp.LATCH_A_ARG1:
            dp.alu_a = dp.registers[self.ir_arg1]
        elif uop == MicroOp.LATCH_A_ARG2:
            dp.alu_a = dp.registers[self.ir_arg2]
        elif uop == MicroOp.LATCH_B_ARG1:
            dp.alu_b = dp.registers[self.ir_arg1]
        elif uop == MicroOp.LATCH_B_ARG2:
            dp.alu_b = dp.registers[self.ir_arg2]

        elif uop in (MicroOp.ALU_ADD, MicroOp.ALU_SUB, MicroOp.ALU_MUL,
                     MicroOp.ALU_DIV, MicroOp.ALU_MOD, MicroOp.ALU_PASS_A,
                     MicroOp.ALU_PASS_B, MicroOp.ALU_CMP):
            dp.execute_alu(uop)

        elif uop == MicroOp.LATCH_REG_ALU:
            target = self.ir_arg3 if self.ir_arg3 != 0 else self.ir_arg1
            dp.registers[target] = dp.alu_out
        elif uop == MicroOp.LATCH_REG_MEM:
            dp.registers[self.ir_arg1] = dp.data_memory_out
        elif uop == MicroOp.LATCH_REG_IMM:
            imm_bytes = self.instr_mem[self.pc]
            val = unpack(">i", imm_bytes)[0]
            dp.registers[self.ir_arg1] = val

        elif uop == MicroOp.CACHE_READ:
            val, penalty = dp.cache.read(dp.alu_out)
            dp.data_memory_out = val
            stall += penalty
        elif uop == MicroOp.CACHE_WRITE:
            penalty = dp.cache.write(dp.alu_out, dp.alu_a)
            stall += penalty

        elif uop == MicroOp.PORT_IN:
            dp.data_memory_out = dp.read_port(self.ir_arg2)
        elif uop == MicroOp.PORT_OUT:
            dp.write_port(self.ir_arg2, dp.alu_a)
        elif uop == MicroOp.LATCH_REG_IN:
            dp.registers[self.ir_arg1] = dp.data_memory_out

        elif uop == MicroOp.JUMP:
            self.pc = dp.registers[self.ir_arg1]
        elif uop == MicroOp.BRANCH_IF_ZERO:
            if dp.zero_flag:
                self.pc = dp.registers[self.ir_arg1]
            else:
                self.pc += 1
        elif uop == MicroOp.BRANCH_IF_NOT_ZERO:
            if not dp.zero_flag:
                self.pc = dp.registers[self.ir_arg1]
            else:
                self.pc += 1

        elif uop == MicroOp.CALL:
            dp.registers[5] = self.pc + 1
            self.pc = dp.registers[self.ir_arg1]
        elif uop == MicroOp.RET:
            self.pc = dp.registers[5]

        dp.registers[0] = 0
        return stall


def simulation(code: list, input_buffer: list, data_mem_size: int, limit: int):
    dp = DataPath(data_mem_size, input_buffer)
    cu = ControlUnit(dp, code)

    try:
        cu.decode_and_execute()
    except StopIteration:
        pass
    except Exception as e:
        logging.error(f"Error during execution: {e}")

    return "".join(dp.output_buffer), cu.tick_count, dp.registers

def main():
    if len(sys.argv) < 2:
        print("Usage: python machine.py <program.bin> [input_file.txt]")
        sys.exit(1)

    code_file = sys.argv[1]
    input_buffer = []
    if len(sys.argv) == 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            input_buffer = list(f.read())

    logging.getLogger().setLevel(logging.DEBUG)

    instructions = read_binary(code_file)
    output, ticks, regs = simulation(instructions, input_buffer, 4096, 10000)

    print(f"\nOutput: {output}")
    print(f"Ticks: {ticks}")

if __name__ == "__main__":
    main()

