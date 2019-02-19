from binaryninja import (
    MediumLevelILInstruction,
    Type,
    MediumLevelILOperation,
    LowLevelILOperation,
    RegisterValueType,
)

from ..bnilvisitor import BNILVisitor
from ..logging import log_debug


class JumpVisitor(BNILVisitor):
    def visit_MLIL_JUMP(self, expr):
        return self.visit(expr.dest)

    def visit_MLIL_LOAD(self, expr):
        return self.visit(expr.src)

    def visit_MLIL_CONST_PTR(self, expr):
        return expr.constant

    visit_MLIL_CONST = visit_MLIL_CONST_PTR


def analyze_indirect_jump(self, expr: MediumLevelILInstruction):
    log_debug("analyze_indirect_jump")
    jump_value = JumpVisitor().visit(expr)

    if jump_value is None:
        log_debug("Jump target not constant")
        return False

    indirect_type = Type.int(self.view.arch.address_size, False)
    indirect_type.const = True

    if not self.view.is_offset_readable(jump_value):
        log_debug("Jump target is not readable")
        return False

    self.view.define_user_data_var(jump_value, indirect_type)
    self.target_queue.put(expr.address)
    return False


def analyze_possible_call(self, expr: MediumLevelILInstruction):
    log_debug("analyze_possible_call")

    if expr.dest.operation != MediumLevelILOperation.MLIL_CONST_PTR:
        return

    if expr.llil.dest.operation != LowLevelILOperation.LLIL_REG_SSA:
        return

    target_reg = expr.llil.dest.src.reg.name

    current_esp = self.function.get_reg_value_at(expr.address, "esp")

    if current_esp.type != RegisterValueType.StackFrameOffset:
        return

    ret_addr = self.function.get_stack_contents_at(expr.address, current_esp.offset, 4)

    if ret_addr.type not in (
        RegisterValueType.ConstantValue,
        RegisterValueType.ConstantPointerValue,
    ):
        return

    if not self.view.is_offset_executable(ret_addr.value):
        return

    # If we got to here, then this is a tail call. Let's define the call
    patch_value = self.view.arch.assemble(f"call {target_reg}", expr.address)

    if self.view.get_instruction_length(expr.address) < len(patch_value):
        log_debug(f"{expr.address:x} is too small for call instruction")
        return

    self.view.write(expr.address, patch_value)

    self.target_queue.put(expr.dest.constant)

    return True
