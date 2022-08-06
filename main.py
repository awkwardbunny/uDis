#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import subprocess
import traceback
from dataclasses import dataclass
from typing import List, Dict, Any, Callable
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

    def newline(self):
        self.buf.append("")

    def append(self, s: str):
        log.error(f"::EMIT {s}")
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
    tab_base = " " * tab_width
    tab_regular = tab_base * depth
    tab_extra = tab_base * (depth + 1)

    tab = tab_regular
    indent_previous: List[Callable] = list()
    indent_extra: Callable = None

    current_block = blocks[name]

    log.info(f"Decompiling block '{name}'")
    log.warning("Decompilation machine broken... Come back tomorrow...")


    """ Known issues
    * Sometimes can't differentiate between string literals and "identifiers"
      (like, `object.thing` vs `"object.thing"`)
      - TODO: I should build AST (?)
      - TODO: Parse back into heirarchical mode, analyze control flow, and break down code blocks
    """
    try:
        history: List[str] = list()
        for bc in current_block.bytecode:
            log.debug(bc)

            offset, op, *args = bc.split()
            offset = int(offset)

            if indent_extra is not None and indent_extra(offset):
                tab = tab_extra
            else:
                tab = tab_regular
                if len(indent_previous) > 0:
                    indent_extra = indent_previous.pop(0)

            match op:
                case "LOAD_CONST_SMALL_INT":
                    stack.push(int(args[0]))
                case "LOAD_CONST_NONE":
                    stack.push(None)
                case "IMPORT_NAME":
                    import_from = stack.pop()
                    _import_level = stack.pop()
                    stack.push({
                        "import_fromlist": import_from,
                        "name": args[0][1:-1]
                    })
                case "IMPORT_FROM":
                    module = stack.peek()
                    name = args[0][1:-1]
                    stack.push({
                        "from": module['name'],
                        "attr": name
                    })
                case "STORE_NAME":
                    val = stack.pop()
                    name = args[0]
                    if history[0] == "IMPORT_NAME":
                        if val['name'].split('.')[-1] == name:
                            buf.append(f"{tab}import {val['name']}")
                        else:
                            buf.append(f"{tab}import {val['name']} as {name}")
                    elif history[0] == "IMPORT_FROM":
                        if val['attr'] == name:
                            buf.append(f"{tab}from {val['from']} import {val['attr']}")
                        else:
                            buf.append(f"{tab}from {val['from']} import {val['attr']} as {name}")
                    elif isinstance(val, dict) and val['type'] == 'cls':
                        buf.newline()
                        buf.append(f"{tab}class {name}:")
                        decompile_code_block(name, blocks, buf, stack, tab_width, depth + 1)
                    elif isinstance(val, dict) and val['type'] == 'func':
                        f_name = val['name']
                        blk = blocks[f_name]
                        buf.newline()
                        buf.append(f"{tab}def {name}({', '.join(blk.args)}):")
                        decompile_code_block(name, blocks, buf, stack, tab_width, depth + 1)
                    elif isinstance(val, str):
                        buf.append(f"{tab}{name} = \"{val}\"")
                    else:
                        log.warning("TODO")
                        buf.append(f"{tab}{name} = {val}")
                case "LOAD_CONST_STRING":
                    stack.push(args[0][1:-1])
                case "BUILD_LIST":
                    list_list = []
                    for _ in range(int(args[0])):
                        list_list.append(stack.pop())
                    stack.push(list(list_list))
                case "BUILD_TUPLE":
                    tuple_list = []
                    for _ in range(int(args[0])):
                        tuple_list.append(stack.pop())
                    stack.push(tuple(tuple_list))
                case "POP_TOP":
                    stack.pop()
                case "LOAD_BUILD_CLASS":
                    stack.push("__builtin__.BUILD_CLASS")
                case "MAKE_FUNCTION":  # Slightly different from CPython
                    desc = args[0]
                    f = list(filter(lambda x: x.descriptor == desc, blocks.values()))[0]
                    stack.push({"type": "func", "name": f.name})
                case "CALL_FUNCTION":
                    argc = int(args[0].split()[0].split('=')[1])
                    argv = [stack.pop() for _ in range(argc)]
                    f = stack.pop()
                    match f.split('.'):
                        case ["__builtin__", *name]:
                            name = '.'.join(name)
                            log.debug(f"Calling {name}({argv})")
                            match name:
                                case "BUILD_CLASS":
                                    stack.push({
                                        'type': "cls",
                                        'name': argv[0],
                                        'func': argv[1]
                                    })
                        case _:
                            stack.push(f"{f}({', '.join(argv)})")
                case "CALL_METHOD":
                    argc = int(args[0].split()[0].split('=')[1])
                    argv = [stack.pop() for _ in range(argc)]
                    f = stack.pop()
                    match f.split('.'):
                        case ["__builtin__", *name]:
                            name = '.'.join(name)
                            log.debug(f"Calling {name}({argv})")
                            match name:
                                case "BUILD_CLASS":
                                    stack.push({
                                        'type': "cls",
                                        'name': argv[0],
                                        'func': argv[1]
                                    })
                        case _:
                            stack.push(f"{f}({', '.join(argv)})")
                case "RETURN_VALUE":
                    buf.append(f"{tab}return {stack.pop()}")
                case "LOAD_NAME":
                    name = args[0]
                    match name:
                        case "__name__":
                            stack.push(current_block.name)
                        case x:
                            log.debug("TODO")
                            stack.push(x)
                case "LOAD_CONST_OBJ":
                    arg = '='.join(' '.join(args).split('=')[1:])
                    if arg[0] == "'":
                        arg = arg[1:-1]
                    stack.push(arg)
                case "STORE_FAST":
                    i = int(args[0])
                    val = stack.pop()
                    if i == len(current_block.args):
                        current_block.args.append(f"local_{i}")
                    if isinstance(val, dict) and val['type'] == 'iterator_value':
                        buf.append(f"{tab}for {current_block.args[i]} in {val['name']}:")

                        def condition(x, l=offset, u=999) -> bool:
                            return l < x < u

                        indent_previous.insert(0, indent_extra)
                        indent_extra = condition
                    else:
                        buf.append(f"{tab}{current_block.args[i]} = {val}")
                case "LOAD_FAST":
                    i = int(args[0])
                    stack.push(current_block.args[i])
                case "LOAD_GLOBAL":
                    stack.push(args[0])
                case "LOAD_ATTR":
                    name = args[0]
                    stack.push(f"{stack.pop()}.{name}")
                case "STORE_ATTR":
                    name = args[0]
                    buf.append(f"{tab}{stack.pop()}.{name} = {stack.pop()}")
                case "LOAD_METHOD":
                    f_name = f"{stack.pop()}.{args[0]}"
                    stack.push(f_name)
                case "LOAD_SUBSCR":  # BINARY_SUBSCR in CPython
                    idx = stack.pop()
                    stack.push(f"{stack.pop()}[{idx}]")
                case "LOAD_CONST_TRUE":
                    stack.push(True)
                case "LOAD_CONST_FALSE":
                    stack.push(False)
                case "FOR_ITER":
                    stack.push({
                        'type': 'iterator_value',
                        'name': stack.peek()['name'],
                    })
                case "GET_ITER_STACK":
                    stack.push({
                        'type': 'iterator',
                        'name': stack.pop(),
                    })
                case "BINARY_OP":
                    i = int(args[0])
                    op = args[1]
                    operands = [stack.pop() for _ in range(i)]
                    operands.reverse()
                    match op:
                        case "__eq__":
                            stack.push(f"{operands[0]} == {operands[1]}")
                        case x:
                            log.warning(f"Unknown operation '{x}'")
                case "POP_JUMP_IF_FALSE":
                    target = int(args[0])

                    def condition(x, l=offset, u=target) -> bool:
                        return l < x < u

                    indent_previous.insert(0, indent_extra)
                    indent_extra = condition
                    buf.append(f"{tab}if {stack.pop()}:")

                case x:
                    log.warning(f"Unknown instruction '{x}' at offset {offset}")

            history.insert(0, op)
            if len(history) > 10:
                history = history[:10]
            log.debug(f"Stack: {stack.dump()}")
    except Exception:
        buf.append(f"ERROR")
        log.error(traceback.format_exc())


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
