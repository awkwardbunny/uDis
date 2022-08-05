#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import List, Dict, Any
from pprint import pprint

import coloredlogs

log = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG")


def get_git_version() -> str:
    status = subprocess.run("git describe --always".split(), capture_output=True)
    return status.stdout.decode().strip()


VERSION = get_git_version()


@dataclass
class CodeBlock:
    name: str
    descriptor: str
    args: List[str]
    bytecode: List[str]

    def set_args(self, args: List[str]):
        self.args = args

    def add_bytecode(self, b: str):
        self.bytecode.append(b)


def disassemble(filename: str) -> Dict[str, CodeBlock]:
    module_name = filename[:-4]
    log.info(f"Disassembling '{module_name}'...")

    # Get disassembly
    status = subprocess.run(f"./micropython/micropython -v -v -v -v -m {module_name}".split(), capture_output=True)
    output = status.stdout.decode().split("\n")

    " Errors can usually be ignored since we are not actually trying to run the files "
    " Uncomment for debug "
    # for e in status.stderr.decode().split("\n"):
    #     log.debug(e)

    code_blocks: Dict[str, CodeBlock] = dict()
    current_block: CodeBlock = None
    for line in output:
        if len(line.strip()) == 0:
            continue
        if line[0] == ' ' or line[0] == '(' or line.startswith("Raw bytecode"):
            continue

        line = line.strip()
        if line.startswith("File"):
            if current_block is not None:
                code_blocks[current_block.name] = current_block

            block_name = line.split("'")[1]
            block_desc = line.split()[6][:-1]
            current_block = CodeBlock(block_name, block_desc, [], [])
            log.info(f"* Code block '{block_name}' ({block_desc})")
            continue

        if line.startswith("arg names:"):
            args = line.split()[2:]
            current_block.set_args(args)
            continue
        current_block.add_bytecode(line)
    if current_block is not None:
        code_blocks[current_block.name] = current_block
    return code_blocks


def write_dis_to_file(cb: Dict[str, CodeBlock], filepath: str):
    log.info(f"Writing disassembly to '{filepath}'")
    with open(filepath, 'w') as out_f:
        for b in cb.values():
            out_f.write(f"# def {b.name}({','.join(b.args)}) #{b.descriptor}\n")
            out_f.write(f"{b.name}:\n")
            for bc in b.bytecode:
                out_f.write(f"  {bc}\n")
            out_f.write("\n")


class Buffer:
    buf: List[str] = list()

    def append(self, s: str):
        log.debug(f">>{s}<<")
        self.buf.append(s)


class Stack:
    buf: List[Any] = list()

    def push(self, v: Any):
        self.buf.insert(0, v)

    def pop(self) -> Any:
        return self.buf.pop(0)

    def dump(self) -> str:
        return f"{self.buf}"

    def peek(self, i: int = 0) -> Any:
        return self.buf[i]


def decompile_code_block(name: str,
                         blocks: Dict[str, CodeBlock],
                         buf: Buffer,
                         stack: Stack,
                         tab_width: int = 4,
                         depth: int = 0):
    tab = " " * tab_width
    current_block = blocks[name]

    log.warning("Decompilation machine broken... Come back tomorrow...")
    return

    history: List[str] = list()
    for bc in current_block.bytecode:
        log.debug(bc)

        offset, op, *args = bc.split()
        offset = int(offset)

        match op:
            case "LOAD_CONST_SMALL_INT":
                stack.push(int(args[0]))
            case "LOAD_CONST_NONE":
                stack.push(None)
            case "IMPORT_NAME":
                import_from = stack.pop()
                import_level = stack.pop()
                stack.push({
                    "import_level": import_level,
                    "import_from": import_from,
                    "name": args[0][1:-1]
                })
            case "IMPORT_FROM":
                module = stack.peek()
                name = args[0][1:-1]
                module['import_from'] = module['name']
                module['name'] = name
                stack.push(module)
            case "STORE_NAME":
                val = stack.peek()
                if history[0].startswith("IMPORT"):
                    if val['import_from'] is not None:
                        if val['name'] == args[0]:
                            buf.append(f"from {val['import_from']} import {val['name']}")
                        else:
                            buf.append(f"from {val['import_from']} import {val['name']} as {args[0]}")
                    else:
                        if val['name'] == args[0]:
                            buf.append(f"import {val['name']}")
                        else:
                            buf.append(f"import {val['name']} as {args[0]}")

                else:
                    log.warning("TODO")
            case "LOAD_CONST_STRING":
                stack.push(args[0][1:-1])
            case "BUILD_TUPLE":
                tuple_list = []
                for _ in range(int(args[0])):
                    tuple_list.append(stack.pop())
                stack.push(tuple(tuple_list))
            case "POP_TOP":
                stack.pop()
            case x:
                log.warning(f"Unknown instruction '{x}' at offset {offset}")

        history.insert(0, op)
        if len(history) > 10:
            history = history[:10]
        log.debug(f"Stack: {stack.dump()}")


def decompile(module_name: str, dis: Dict[str, CodeBlock], fn_dec: str):
    log.info(f"Decompiling '{module_name}'...")
    timestamp = datetime.datetime.now()

    buf = Buffer()
    stack = Stack()
    decompile_code_block('<module>', dis, buf, stack)

    with open(fn_dec, 'w') as out_f:
        out_f.write(f"####################################\n")
        out_f.write(f"## Decompiled with uDis ({VERSION}) ##\n")
        out_f.write(f"## At: {timestamp} ##\n")
        out_f.write(f"####################################\n\n")
        for line in buf.buf:
            out_f.write(f"{line}\n")


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

        dis = disassemble(fn_mpy)
        write_dis_to_file(dis, fn_asm)
        decompile(module_name, dis, fn_dec)
    log.info("Done.")


if __name__ == "__main__":
    main()
