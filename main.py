#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import subprocess
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import List, Dict, Any, Union, Iterator
from pprint import pprint, pformat
from enum import Enum, auto
import ast

import coloredlogs

log = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG")


def get_git_version() -> str:
    status = subprocess.run("git describe --always".split(), capture_output=True)
    return status.stdout.decode().strip()


VERSION = get_git_version()


def getGrammar(fn: str) -> str:
    with open(fn, 'r') as f:
        return f.read()


@dataclass
class Bytecode:
    offset: int
    opcode: str
    operands: str
    lineno: Union[int | None]
    attr: Dict[Any, Any] = field(default_factory=dict)

    def get_opcode(self) -> str:
        return self.opcode

    def line_str(self) -> str:
        return f"   # line {self.lineno}" if self.lineno is not None else ""

    def __str__(self) -> str:
        return f"{self.offset} {self.opcode} {self.operands}{self.line_str()}"


@dataclass
class CodeBlock:
    name: str
    source: str
    desc: str
    args: List[str]
    code: Dict[int, Bytecode]

    def set_args(self, args: List[str]):
        self.args = args

    def add_bytecode(self, b: Bytecode):
        self.code[b.offset] = b


class Buffer:
    buf: List[str]

    def __init__(self):
        self.buf = []

    def print(self, s: str = ""):
        self.write(s+"\n")

    def write(self, s: str, print: bool = False):
        if print:
            log.error(f"::EMIT {s}")
        self.buf.append(s)

    def dump(self) -> str:
        return ''.join(self.buf)


class uDisObjType(Enum):
    CONST = auto()
    MODULE = auto()
    VARIABLE = auto()


@dataclass()
class uDisObj:
    ty: uDisObjType
    val: Any


def astStr(self):
    return f"{self.__class__.__name__}: {vars(self)}"


ast.AST.__str__ = astStr
ast.AST.__repr__ = astStr


class Stack:
    data: List[ast.AST]

    def __init__(self):
        self.data = []

    def push(self, v: ast.AST):
        self.data.insert(0, v)

    def pop(self) -> ast.AST:
        return self.data.pop(0)

    def peek(self, i: int = 0) -> ast.AST:
        return self.data[i]

    def dump(self, limit: int = 0) -> str:
        output = "Stack:\n"
        num = len(self.data) - 1
        for d in self.data if limit == 0 else self.data[:limit]:
            if isinstance(d, ast.AST):
                output += f" {num} - {ast.dump(d)}\n"
            else:
                output += f" {num} - {d}\n"
            num -= 1
        return output
        # return pformat(self.data if limit is 0 else self.data[:limit])


class uDecompiler:
    filename: str
    module_name: str

    stack: Stack
    tab: str = " " * 4
    blocks: Dict[str, CodeBlock] = None

    def __init__(self, mpy_fn: str, module_name: str):
        self.filename = mpy_fn
        self.module_name = module_name
        self.stack = Stack()

    def disassemble(self):
        log.info("Disassembling")

        # Get disassembly
        status = subprocess.run(f"./micropython/micropython -v -v -v -v -m {self.filename}".split(), capture_output=True)
        output = status.stdout.decode().split("\n")

        " Errors can usually be ignored since we are not actually trying to run the files "
        " Uncomment for debug "
        # for e in status.stderr.decode().split("\n"):
        #     log.debug(e)

        self.blocks: Dict[str, CodeBlock] = {}
        lineinfo: Dict[int, int] = {}

        current_block: CodeBlock = None
        for line in output:
            print(line)
            if line.startswith("mem"):
                break  # end of disassmbly
            if len(line.strip()) == 0:
                continue
            if line[0] == '(' or line.startswith("Raw bytecode"):
                continue

            # Source line information
            if line.startswith("  "):
                parts = line.strip().split()
                bc = int(parts[0].split('=')[1])  # bc=x
                line = int(parts[1].split('=')[1])  # line=x
                lineinfo[bc] = line
                continue

            if line[0] == ' ':
                continue

            line = line.strip()
            if line.startswith("File"):
                if current_block is not None:
                    self.blocks[current_block.desc] = current_block

                source_name = line[5:].split(',')[0]
                block_name = line.split("'")[1]
                block_desc = line.split()[6][:-1]
                current_block = CodeBlock(block_name, source_name, block_desc, [], {})
                log.info(f"* Code block '{block_name}' ({block_desc})")
                continue

            if line.startswith("arg names:"):
                args = line.split()[2:]
                current_block.set_args(args)
                continue

            parts = line.split()

            # HACKY: handle edge case where a newline inside const was printed
            try:
                num = int(parts[0])
            except ValueError:
                last = current_block.code[list(current_block.code)[-1]]
                last.operands += "\n" + line
                continue

            instr = parts[1]
            operands = ' '.join(parts[2:])
            lineno = lineinfo[num] if num in lineinfo.keys() else None
            current_block.add_bytecode(Bytecode(num, instr, operands, lineno))
        if current_block is not None:
            self.blocks[current_block.desc] = current_block

    def get_disassembly(self) -> str:
        if self.blocks is None:
            self.disassemble()

        timestamp = datetime.datetime.now()

        buf = Buffer()
        buf.print(f"######################################")
        buf.print(f"## Disassembled with uDis ({VERSION}) ##")
        buf.print(f"## At: {timestamp}   ##")
        buf.print(f"######################################\n")

        for block in self.blocks.values():
            buf.print(f"## Source: {block.source}")
            buf.print(f"## Name:   {block.name}")
            buf.print(f"## Args:   {block.args}")

            for bc in block.code.values():
                if bc.lineno is not None:
                    buf.print()
                if bc.opcode == "MAKE_FUNCTION":
                    func_name = self.blocks[bc.operands].name
                    buf.print(f"{bc.opcode} {bc.operands}({func_name}){bc.line_str()}")
                else:
                    buf.print(f"{bc.opcode} {bc.operands}{bc.line_str()}")
            buf.print()
        buf.print()
        return buf.dump()

    def pass_0(self, desc: str) -> List[ast.AST]:

        cb = self.blocks[desc]
        log.debug(f"Processing {cb.name}({cb.desc})")
        tree: List[ast.stmt] = list()

        aux_stack = Stack()

        instrs = list(cb.code.values())
        for instr, next in zip_longest(instrs, instrs[1:]):
            log.debug(f"OPCODE: \"{instr.opcode} {instr.operands}\"")
            match instr.opcode:
                case "LOAD_CONST_SMALL_INT":
                    self.stack.push(ast.Constant(int(instr.operands)))
                case "LOAD_CONST_NONE":
                    self.stack.push(ast.Constant(None))
                case "LOAD_CONST_TRUE":
                    self.stack.push(ast.Constant(True))
                case "LOAD_CONST_FALSE":
                    self.stack.push(ast.Constant(False))
                case "LOAD_CONST_STRING":
                    self.stack.push(ast.Constant(instr.operands[1:-1]))
                case "LOAD_CONST_OBJ":
                    data = '='.join(instr.operands.split('=')[1:])
                    self.stack.push(ast.Constant(data[1:-1]))
                case "LOAD_NAME":
                    self.stack.push(ast.Name(instr.operands, ast.Load()))
                case "IMPORT_NAME":
                    fromlist = self.stack.pop()
                    level = self.stack.pop()
                    if isinstance(fromlist, ast.Constant) and fromlist.value is None:
                        a = ast.alias(instr.operands[1:-1])
                        x = ast.Import([a])
                        aux_stack.push(instr.operands[1:-1])
                        self.stack.push(x)
                    elif isinstance(fromlist, ast.Tuple):
                        a = [ast.alias(n.value) for n in fromlist.elts]
                        for n in fromlist.elts:
                            aux_stack.push(n.value)
                        x = ast.Import(a)
                        self.stack.push(x)
                        aux_stack.push(instr.operands[1:-1])
                case "IMPORT_FROM":
                    i = self.stack.peek()
                    if isinstance(i, ast.Import):
                        ii = ast.ImportFrom(aux_stack.pop(), i.names, 0)
                        self.stack.push(ii)
                    else:
                        ii = i
                case "STORE_NAME":
                    if len(aux_stack.data) != 0:
                        orig_name = aux_stack.pop()
                        if orig_name != instr.operands:
                            a = None
                            for x in self.stack.peek().names:
                                if x.name == orig_name:
                                    a = x
                                    print("A")
                            a.asname = instr.operands
                        if len(aux_stack.data) == 0:
                            tree.append(self.stack.pop())
                    else:
                        if isinstance(self.stack.peek(), ast.FunctionDef):
                            tree.append(self.stack.pop())
                        elif isinstance(self.stack.peek(), ast.ClassDef):
                            self.stack.pop()
                        else:
                            x = ast.Assign([ast.Name(instr.operands, ast.Store())], self.stack.pop())
                            x.lineno = None  # ?
                            tree.append(x)
                case "BUILD_TUPLE":
                    n = int(instr.operands)
                    l = [self.stack.pop() for _ in range(n)]
                    t = tuple(l)
                    self.stack.push(ast.Tuple(l))
                case "BUILD_LIST":
                    n = int(instr.operands)
                    l = [self.stack.pop() for _ in range(n)]
                    self.stack.push(ast.List(l))
                case "POP_TOP":
                    self.stack.pop()
                case "LOAD_BUILD_CLASS":
                    # self.stack.push(ast.ClassDef())
                    aux_stack.push("BUILD_CLASS")
                case "MAKE_FUNCTION":
                    fcb = self.blocks[instr.operands]
                    args = ast.arguments([], [ast.arg(x) for x in fcb.args], None, [], [], None, [])
                    x = ast.FunctionDef(fcb.name, args, self.pass_0(instr.operands))
                    x.decorator_list = []
                    x.lineno = None
                    self.stack.push(x)
                case "RETURN_VALUE":
                    tree.append(ast.Return(self.stack.pop()))
                case "CALL_FUNCTION":
                    if len(aux_stack.data) > 0 and aux_stack.peek() == "BUILD_CLASS":
                        name = self.stack.pop()
                        cls = self.stack.pop()
                        cls = ast.ClassDef(name.value, [], {}, cls.body, [])
                        tree.append(cls)
                        aux_stack.pop()
                        self.stack.push(cls)
                    else:
                        parts = instr.operands.split()
                        n = int(parts[0].split('=')[1])
                        nkw = int(parts[1].split('=')[1])
                        kwargs = {}
                        for _ in range(nkw):
                            kwargs[self.stack.pop()] = self.stack.pop()
                        args = [self.stack.pop() for _ in range(n)]
                        self.stack.push(ast.Call(self.stack.pop(), args, kwargs))
                        if next.opcode == "POP_TOP":
                            tree.append(self.stack.peek())
                case "LOAD_GLOBAL":
                    self.stack.push(ast.Name(instr.operands, ast.Load()))
                case "LOAD_METHOD":
                    self.stack.push(ast.Attribute(self.stack.pop(), instr.operands))
                    # self.stack.peek().id += f".{instr.operands}"
                case "LOAD_FAST":
                    n = int(instr.operands)
                    if n < len(cb.args):
                        self.stack.push(ast.Name(cb.args[n], ast.Load()))
                    else:
                        self.stack.push(ast.Name(f"local_{n-len(cb.args)}", ast.Load()))
                case "STORE_FAST":
                    n = int(instr.operands)
                    if n < len(cb.args):
                        v = ast.Name(cb.args[n], ast.Store())
                    else:
                        v = ast.Name(f"local_{n-len(cb.args)}", ast.Store())
                    x = ast.Assign([v], self.stack.pop())
                    x.lineno = None
                    tree.append(x)
                case "LOAD_ATTR":
                    a = ast.Attribute(self.stack.pop(), instr.operands, ast.Load())
                    self.stack.push(a)
                case "LOAD_SUBSCR":
                    sub = self.stack.pop()
                    a = ast.Subscript(self.stack.pop(), sub, ast.Load())
                    self.stack.push(a)
                case "STORE_ATTR":
                    obj = self.stack.pop()
                    a = ast.Assign([ast.Attribute(obj, instr.operands, ast.Store())], self.stack.pop())
                    a.lineno = None
                    tree.append(a)
                case "CALL_METHOD":
                    parts = instr.operands.split()
                    n = int(parts[0].split('=')[1])
                    nkw = int(parts[1].split('=')[1])
                    kwargs = []
                    for _ in range(nkw):
                        val = self.stack.pop()
                        kwargs.append(ast.keyword(self.stack.pop().value, val))
                    args = [self.stack.pop() for _ in range(n)]
                    self.stack.push(ast.Call(self.stack.pop(), args, kwargs))
                    if next.opcode == "POP_TOP":
                        tree.append(self.stack.peek())
                case "DUP_TOP":
                    self.stack.push(self.stack.peek())
                case "GET_ITER_STACK":
                    self.stack.pop()
                    break  # TODO
                case "BINARY_OP":
                    match instr.operands.split():
                        case [n, "__gt__"]:
                            n = int(n)
                            nl = [self.stack.pop() for _ in range(n)]
                            self.stack.push(ast.Compare(self.stack.pop(), [ast.Gt()], nl))
                        case [n, "__iadd__"]:
                            r = self.stack.pop()
                            # tree.append(ast.Assign(x, ast.BinOp(x, ast.Add(), ast.Constant(n))))
                            self.stack.push(ast.BinOp(self.stack.pop(), ast.Add(), r))
                        case [n, "__isub__"]:
                            r = self.stack.pop()
                            # tree.append(ast.Assign(x, ast.BinOp(x, ast.Add(), ast.Constant(n))))
                            self.stack.push(ast.BinOp(self.stack.pop(), ast.Sub(), r))
                        case [n, "__add__"]:
                            r = self.stack.pop()
                            self.stack.push(ast.BinOp(self.stack.pop(), ast.Add(), r))
                        case x:
                            log.warning("AH")
                case "ROT_TWO":
                    a = self.stack.pop()
                    b = self.stack.pop()
                    self.stack.push(a)
                    self.stack.push(b)
                case "ROT_THREE":
                    a = self.stack.pop()
                    b = self.stack.pop()
                    c = self.stack.pop()
                    self.stack.push(b)
                    self.stack.push(c)
                    self.stack.push(a)
                case "POP_JUMP_IF_TRUE":
                    self.stack.pop()
                    break  # TODO
                case "FOR_ITER":
                    aux_stack.push(int(instr.operands)+instr.offset)
                case x:
                    log.warning(f"Unknown \"{x}\"")
            print(self.stack.dump(5))
            print(aux_stack.dump(5))
            # pprint(tree)
            for x in tree:
                print(ast.dump(x))
            # if cb.name.startswith("move"):
            #     input()

        return tree

    def decompile(self, top_name: str = "<module>") -> str:
        if self.blocks is None:
            self.disassemble()

        log.info("Decompiling")
        timestamp = datetime.datetime.now()

        buf = Buffer()
        buf.print(f"####################################")
        buf.print(f"## Decompiled with uDis ({VERSION}) ##")
        buf.print(f"## At: {timestamp} ##")
        buf.print(f"####################################\n")

        top_desc = None
        for cb in self.blocks.values():
            if cb.name == top_name:
                top_desc = cb.desc
                break

        if top_desc is None:
            log.error(f"Unable to find code block \'{top_name}\'")
            return "ERROR"

        statements = self.pass_0(top_desc)
        mod = ast.Module(statements, [])

        print("\n=============\n")
        print(ast.dump(mod, indent=4))
        print("\n=============\n")

        lines = ast.unparse(mod).split('\n')
        for l in lines:
            buf.write(f"{l}\n")
        # trees = {}
        # for block in self.blocks.values():
        #     trees[block.desc] = self.parser.parse(block)

        buf.print()
        return buf.dump()


def main(args: List[str] = None):
    log.info(f" *** uDis MicroPython Decompiler ({VERSION}) *** ")
    parser = argparse.ArgumentParser(description='Decompile MicroPython modules')
    parser.add_argument('input_dir', type=str, help='Input directory containing mpy files')
    parser.add_argument('output_dir', type=str, help='Output directory')
    args = parser.parse_args(args)

    for in_f in os.listdir(os.fsencode(args.input_dir)):
        fn = os.fsdecode(in_f)
        if fn[-4:] != ".mpy":
            continue

        module_name = f"{fn[:-4]}"
        fn_mpy = f"{args.input_dir}/{fn}"
        fn_asm = f"{args.output_dir}/{module_name}.s"
        fn_dec = f"{args.output_dir}/{module_name}.py"

        d = uDecompiler(fn_mpy, module_name)
        dis = d.get_disassembly()
        with open(fn_asm, 'w') as f_asm:
            f_asm.write(dis)

        dec = d.decompile()
        with open(fn_dec, 'w') as f_dec:
            f_dec.write(dec)
    log.info("Done.")


if __name__ == "__main__":
    main()
