from enum import Enum, auto
from isa import Opcode

class MicroOp(Enum):
    """
    Микро-операции (микроинструкции), выполняющие управление DataPath.
    RISC Harvard архитектура:
    - Инструкции и данные лежат в разной памяти.
    - Выборка инструкции (Fetch) происходит автоматически за 1 такт вместе с выполнением или требует отдельного такта,
    но так как Гарвард, можно делать fetch и data read одновременно. Но мы сделаем честный процесс по тактам (tick).
    """

    # --- Управление потоком команд ---
    LATCH_PC_INC = auto()     # PC <- PC + 1
    LATCH_PC_ALU = auto()     # PC <- ALU_OUT (прыжки)

    # --- Выборка инструкции (Fetch) ---
    LATCH_IR = auto()         # IR <- InstructionMemory[PC]

    # --- Подготовка операндов для АЛУ ---
    LATCH_A_ARG1 = auto()     # Рег A АЛУ <- GPR[arg1]
    LATCH_A_ARG2 = auto()     # Рег A АЛУ <- GPR[arg2]
    LATCH_A_RES  = auto()     # Рег A <- ALU_OUT
    LATCH_B_ARG1 = auto()     # Рег B АЛУ <- GPR[arg1]
    LATCH_B_ARG2 = auto()     # Рег B АЛУ <- GPR[arg2]

    # --- Операции АЛУ ---
    ALU_ADD = auto()          # ALU_OUT <- A + B
    ALU_SUB = auto()          # ALU_OUT <- A - B
    ALU_MUL = auto()          # ALU_OUT <- A * B
    ALU_DIV = auto()          # ALU_OUT <- A // B
    ALU_MOD = auto()          # ALU_OUT <- A % B
    ALU_PASS_A = auto()       # ALU_OUT <- A
    ALU_PASS_B = auto()       # ALU_OUT <- B
    ALU_CMP = auto()          # Установить флаги Zero, Neg по результату A - B

    # --- Запись результата ---
    LATCH_REG_ALU = auto()    # GPR[arg1] <- ALU_OUT (или arg3 в случае трехадресных)
    LATCH_REG_MEM = auto()    # GPR[arg1] <- DataMemory_OUT
    LATCH_REG_IMM = auto()    # GPR[arg1] <- IR.imm
    LATCH_REG_IN  = auto()    # GPR[arg1] <- Port_IN

    # --- Работа с памятью данных (Кэш) ---
    CACHE_READ = auto()       # Сигнал DataMemory (Cache) на чтение по адресу из ALU_OUT (или из GPR[arg2])
    CACHE_WRITE = auto()      # Сигнал DataMemory на запись данных GPR[arg1] по адресу GPR[arg2]

    # --- Ввод/Вывод ---
    PORT_IN = auto()          # Чтение из порта arg2 в GPR[arg1]
    PORT_OUT = auto()         # Запись GPR[arg1] в порт arg2

    # --- Переходы ---
    BRANCH_IF_ZERO = auto()   # Если Zero==1: PC <- GPR[arg1], иначе PC <- PC + 1
    BRANCH_IF_NOT_ZERO = auto() # Если Zero==0: PC <- GPR[arg1], иначе PC <- PC + 1
    JUMP = auto()             # PC <- GPR[arg1]
    CALL = auto()             # Сохранить PC в GPR[R5(стек возврата)], PC <- GPR[arg1]
    RET = auto()              # PC <- снять со стека возврата

    # --- Завершение ---
    FINISH_INSTRUCTION = auto()
    HALT_PROCESSOR = auto()


def get_microcode_rom() -> dict[Opcode, list[MicroOp]]:
    """
    Фабрика микрокода. Каждой инструкции из ISA сопоставляется список микрокоманд.
    Первая фаза всегда FETCH (выборка из Instr_Mem).
    """
    fetch_cycle = [
        MicroOp.LATCH_IR,        # Загрузить инструкцию по адресу PC
        MicroOp.LATCH_PC_INC     # Увеличить PC
    ]

    microcode = {
        Opcode.ADD: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_ADD,
            MicroOp.LATCH_REG_ALU, # результат в arg3
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.SUB: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_SUB,
            MicroOp.LATCH_REG_ALU,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.MUL: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_MUL,
            MicroOp.LATCH_REG_ALU,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.DIV: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_DIV,
            MicroOp.LATCH_REG_ALU,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.MOD: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_MOD,
            MicroOp.LATCH_REG_ALU,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.CMP: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.LATCH_B_ARG2,
            MicroOp.ALU_CMP,
            MicroOp.FINISH_INSTRUCTION
        ],

        Opcode.LD: [
            MicroOp.LATCH_B_ARG2, # адрес из arg2
            MicroOp.ALU_PASS_B,
            MicroOp.CACHE_READ,   # читаем в DataMem_OUT
            MicroOp.LATCH_REG_MEM,# GPR[arg1] = DataMem_OUT
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.ST: [
            MicroOp.LATCH_A_ARG1, # данные
            MicroOp.LATCH_B_ARG2, # адрес
            MicroOp.ALU_PASS_B,
            MicroOp.CACHE_WRITE,  # пишем данные по адресу
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.LDI: [
            MicroOp.LATCH_REG_IMM, # В IR у нас есть костыль с 2 словами для LDI (надо будет реализовать чтение второго слова)
            MicroOp.LATCH_PC_INC,  # Перепрыгиваем второе слово, так как оно - константа
            MicroOp.FINISH_INSTRUCTION
        ],

        Opcode.IN: [
            MicroOp.PORT_IN,
            MicroOp.LATCH_REG_IN,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.OUT: [
            MicroOp.LATCH_A_ARG1,
            MicroOp.PORT_OUT,
            MicroOp.FINISH_INSTRUCTION
        ],

        Opcode.JMP: [
            MicroOp.JUMP,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.JZ: [
            MicroOp.BRANCH_IF_ZERO,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.JNZ: [
            MicroOp.BRANCH_IF_NOT_ZERO,
            MicroOp.FINISH_INSTRUCTION
        ],

        Opcode.CALL: [
            MicroOp.CALL,
            MicroOp.FINISH_INSTRUCTION
        ],
        Opcode.RET: [
            MicroOp.RET,
            MicroOp.FINISH_INSTRUCTION
        ],

        Opcode.HLT: [
            MicroOp.HALT_PROCESSOR
        ]
    }

    return {op: fetch_cycle + ops for op, ops in microcode.items()}

